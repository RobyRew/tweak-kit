TARGET := iphone:clang:latest:14.0
ARCHS := arm64

include $(THEOS)/makefiles/common.mk

TWEAK_NAME := zxPluginsInject

# Self-contained: fishhook ships alongside SideloadFix here (the tweak-kit copy
# is the canonical one; consumers do not reach back into another repo's Sources).
zxPluginsInject_FILES := SideloadFix.xm fishhook.m
zxPluginsInject_CFLAGS := -fobjc-arc -Os -Iinclude
zxPluginsInject_LOGOS_DEFAULT_GENERATOR := internal

include $(THEOS_MAKE_PATH)/tweak.mk
