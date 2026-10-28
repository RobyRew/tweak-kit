#!/usr/bin/env python3
"""Mach-O ObjC metadata inventory for the Spotify binary.

Parses __objc_classlist / __objc_catlist / __objc_protolist and dumps:
  classes.txt    class_name<TAB>addr<TAB>superclass_name
  methods.txt    class_name<TAB>+/-<TAB>selector<TAB>imp_addr
  protocols.txt  protocol_name<TAB>addr
  categories.txt category_name<TAB>+/-<TAB>selector<TAB>imp_addr  (class: first line)
Handles Xcode 15+ relative method lists (offsets instead of pointers).

Usage: objcinventory.py <mach-o> <outdir>
"""
import struct
import sys
import os
import re

MAGIC64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_CHAINED_FIXUPS = 0x80000034
REL_FLAG = 0x8000_0000


class MachO:
    def __init__(self, data):
        self.data = data
        magic, = struct.unpack_from("<I", data, 0)
        assert magic == MAGIC64, hex(magic)
        self.ncmds, = struct.unpack_from("<I", data, 16)
        self.segments = []       # (name, vmaddr, vmsize, fileoff, filesize)
        self.sections = {}       # name -> (addr, size, offset, segname)
        self.ptr_format = {}     # segname -> chained pointer format (or None)
        self._parse_load_commands()

    def _parse_load_commands(self):
        off = 32
        for _ in range(self.ncmds):
            cmd, cmdsize = struct.unpack_from("<II", self.data, off)
            if cmd == LC_SEGMENT_64:
                name = self.data[off + 8:off + 24].split(b"\0")[0].decode()
                vmaddr, vmsize, fileoff, filesize, _mp, _ip, nsects, _fl = \
                    struct.unpack_from("<QQQQiiII", self.data, off + 24)
                self.segments.append((name, vmaddr, vmsize, fileoff, filesize))
                so = off + 72
                for _ in range(nsects):
                    sn = self.data[so:so + 16].split(b"\0")[0].decode()
                    addr, size, s_off = struct.unpack_from("<QQI", self.data, so + 32)
                    self.sections[sn] = (addr, size, s_off, name)
                    so += 80
            elif cmd == LC_CHAINED_FIXUPS:
                self._parse_fixups(off)
            off += cmdsize

    def _parse_fixups(self, cmd_off):
        dataoff, _datasize = struct.unpack_from("<II", self.data, cmd_off + 8)
        base = dataoff
        _ver, starts_off, _imp_off, _sym_off, _imp_n, _imp_f, _sym_f = \
            struct.unpack_from("<IIIIIII", self.data, base)
        seg_count, = struct.unpack_from("<I", self.data, base + starts_off)
        # map segment index -> name (order of LC_SEGMENT_64, incl. __PAGEZERO)
        seg_names = [n for n, _vm, _vs, _fo, _fs in self.segments]
        for s in range(seg_count):
            seg_off, = struct.unpack_from("<I", self.data, base + starts_off + 4 + 4 * s)
            if seg_off == 0 or s >= len(seg_names):
                continue
            p = base + starts_off + seg_off
            _size, _page_size, ptr_fmt, _seg_off_vm, _max_valid, _page_count = \
                struct.unpack_from("<IHHQI H", self.data, p)
            self.ptr_format[seg_names[s]] = ptr_fmt

    def va2off(self, va):
        if va == 0:
            return None
        for name, vm, vs, fo, fs in self.segments:
            if vm <= va < vm + fs:
                return fo + (va - vm)
        return None

    def seg_for_va(self, va):
        for name, vm, vs, fo, fs in self.segments:
            if vm <= va < vm + fs:
                return name
        return None

    def u64(self, va):
        o = self.va2off(va)
        if o is None:
            return None
        try:
            return struct.unpack_from("<Q", self.data, o)[0]
        except struct.error:
            return None

    def u64p(self, va):
        """Read a pointer field, using dyld_info's fixup table as truth.

        Rebase entries store the decoded target; bind entries carry the
        imported symbol name (returned as a string). Falls back to the
        validated low32-offset rule for fields not listed (should not occur
        on the paths this inventory walks).
        """
        entry = self.fixups.get(va)
        if entry is not None:
            return entry
        raw = self.u64(va)
        if raw is None or raw == 0:
            return None
        return 0x100000000 + (raw & 0xFFFFFFFF)

    def load_fixups(self, path):
        """Parse dyld_info -fixups output: field_va -> target int or symbol."""
        self.fixups = {}
        pat = re.compile(
            r"^\s*(\S+)\s+(\S+)\s+(0x[0-9A-Fa-f]+)\s+(rebase|bind)\s+(.+)$")
        with open(path) as f:
            for ln in f:
                m = pat.match(ln)
                if not m:
                    continue
                field = int(m.group(3), 16)
                if m.group(4) == "rebase":
                    self.fixups[field] = int(m.group(5), 16)
                else:
                    sym = m.group(5).strip()
                    if sym.startswith("libobjc/_OBJC_CLASS_$_"):
                        self.fixups[field] = sym[len("libobjc/_OBJC_CLASS_$_"):]
                    elif sym.startswith("libobjc/_OBJC_METACLASS_$_"):
                        self.fixups[field] = sym[len("libobjc/_OBJC_METACLASS_$_"):]
                    else:
                        self.fixups[field] = sym

    def i32(self, va):
        o = self.va2off(va)
        if o is None:
            return None
        try:
            return struct.unpack_from("<i", self.data, o)[0]
        except struct.error:
            return None

    def u32(self, va):
        o = self.va2off(va)
        if o is None:
            return None
        try:
            return struct.unpack_from("<I", self.data, o)[0]
        except struct.error:
            return None

    def cstring(self, va, limit=256):
        o = self.va2off(va)
        if o is None:
            return None
        end = self.data.find(b"\0", o, o + limit)
        if end < 0:
            return None
        try:
            return self.data[o:end].decode("utf-8", "replace")
        except Exception:
            return None

    def section(self, name):
        return self.sections.get(name)

    def walk_ptrs(self, secname):
        sec = self.section(secname)
        if sec is None:
            return
        addr, size, s_off, _seg = sec
        n = size // 8
        for i in range(n):
            p = self.u64p(addr + 8 * i)
            if p:
                yield p

    def class_ro(self, cls_va):
        """class_t (40B: isa,super,cache,vtable,data) -> class_ro_t dict.

        data carries low-bit flags (FAST_IS_SWIFT_*), masked off.
        """
        data_va = self.u64p(cls_va + 32)
        if data_va is None or not isinstance(data_va, int):
            return None
        ro_va = data_va & ~0x7
        # class_ro_t: flags@0..reserved@12, ivarLayout@16, name@24,
        # baseMethodList@32, baseProtocols@40, ivars@48, weakIvarLayout@56,
        # baseProperties@64
        name_va = self.u64p(ro_va + 24)
        name = None
        if isinstance(name_va, int) and name_va:
            name = self.cstring(name_va)
            if name is not None and not (1 < len(name) < 200 and
                                         re.fullmatch(r"[\x20-\x7e]+", name)):
                name = None
        mlist_va = self.u64p(ro_va + 32)
        return {"ro": ro_va, "name": name, "methods": mlist_va}

    def methods(self, mlist_va):
        """Yield (selector, imp_va) from a method list (classic or relative)."""
        if not mlist_va:
            return
        entsize_flags = self.u32(mlist_va)
        if entsize_flags is None:
            return
        count = self.u32(mlist_va + 4)
        if count is None or count > 10000:
            return
        if entsize_flags & REL_FLAG:
            entsize = entsize_flags & ~REL_FLAG
            if entsize < 12:
                return
            for i in range(count):
                e = mlist_va + 8 + i * entsize
                sel_off = self.i32(e)
                imp_off = self.i32(e + 8)
                if sel_off is None or imp_off is None:
                    continue
                # sel_off is relative to the entry and lands on a pointer
                # slot (chained-fixup location) holding the real selector
                # address; resolve through the fixup table.
                slot = e + sel_off
                target = self.fixups.get(slot)
                if target is None and isinstance(target, type(None)):
                    raw = self.u64(slot)
                    if raw:
                        target = 0x100000000 + (raw & 0xFFFFFFFF)
                sel = self.cstring(target) if isinstance(target, int) else None
                imp = e + 8 + imp_off
                if sel:
                    yield sel, imp
        else:
            for i in range(count):
                e = mlist_va + 8 + i * 24
                name_va = self.u64p(e)
                imp_va = self.u64p(e + 16)
                sel = self.cstring(name_va) if name_va else None
                if sel:
                    yield sel, imp_va


def main():
    path, outdir = sys.argv[1], sys.argv[2]
    fixups_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(outdir, "fixups.txt")
    os.makedirs(outdir, exist_ok=True)
    with open(path, "rb") as f:
        data = f.read()
    m = MachO(data)
    m.load_fixups(fixups_path)

    class_by_addr = {}

    def write_methods(out, cls_label, is_class, mlist_va):
        for sel, imp in m.methods(mlist_va):
            prefix = "+" if is_class else "-"
            out.write(f"{cls_label}\t{prefix}\t{sel}\t{imp if imp is None else hex(imp)}\n")

    n_cls = 0
    with open(os.path.join(outdir, "classes.txt"), "w") as cls_out:
        for p in m.walk_ptrs("__objc_classlist"):
            ro = m.class_ro(p)
            if ro is None or ro["name"] is None:
                continue
            super_val = m.u64p(p + 8)
            super_name = None
            if isinstance(super_val, str):
                super_name = super_val  # bind import, e.g. NSObject
            elif isinstance(super_val, int) and super_val:
                sro = m.class_ro(super_val)
                if sro:
                    super_name = sro["name"]
            class_by_addr[p] = ro["name"]
            cls_out.write(f"{ro['name']}\t{hex(p)}\t{super_name or ''}\n")
            n_cls += 1

    with open(os.path.join(outdir, "methods.txt"), "w") as m_out:
        for p in m.walk_ptrs("__objc_classlist"):
            ro = m.class_ro(p)
            if ro is None or ro["name"] is None:
                continue
            write_methods(m_out, ro["name"], False, ro["methods"])

    n_cat = 0
    with open(os.path.join(outdir, "categories.txt"), "w") as c_out:
        for secname in ("__objc_catlist", "__objc_catlist2", "__objc_nlcatlist"):
            for p in m.walk_ptrs(secname):
                # category_t: name, cls, instMethods, classMethods, protocols, instProps
                name_va = m.u64p(p)
                cls_va = m.u64p(p + 8)
                inst = m.u64p(p + 16)
                clsm = m.u64p(p + 24)
                name = m.cstring(name_va) if name_va else None
                if isinstance(cls_va, str):
                    target = cls_va
                else:
                    target = class_by_addr.get(cls_va) or (m.cstring(cls_va) if cls_va else "?")
                c_out.write(f"CAT\t{name or '?'}\t{target or '?'}\n")
                write_methods(c_out, f"({name or '?'})", False, inst)
                write_methods(c_out, f"({name or '?'})", True, clsm)
                n_cat += 1

    n_proto = 0
    with open(os.path.join(outdir, "protocols.txt"), "w") as p_out:
        for p in m.walk_ptrs("__objc_protolist"):
            name_va = m.u64p(p + 8)
            name = m.cstring(name_va) if name_va else None
            if name:
                p_out.write(f"{name}\t{hex(p)}\n")
                n_proto += 1

    print(f"classes: {n_cls}")
    print(f"categories: {n_cat}")
    print(f"protocols: {n_proto}")
    sec = m.section("__objc_methlist")
    print(f"__objc_methlist: {sec[0]:#x} size {sec[1]:#x}")
    sec = m.section("__objc_classname")
    print(f"__objc_classname: {sec[0]:#x} size {sec[1]:#x}")


if __name__ == "__main__":
    main()
