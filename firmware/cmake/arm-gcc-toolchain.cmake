# Cross-compilation toolchain file for the benchmark firmware (Arm GNU, bare metal).
# The CPU flags come from the project's CMakeLists (CPU_FLAGS).
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER   arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY      arm-none-eabi-objcopy)
set(CMAKE_SIZE         arm-none-eabi-size)

# Firmware links with its own linker script; never try to link a host test binary.
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

# Reproducibility: identical output regardless of checkout path or build time.
# (SOURCE_DATE_EPOCH is exported by the toolchain image and by tools/build-firmware.py.)
add_compile_options(
    -ffile-prefix-map=${CMAKE_SOURCE_DIR}=.
    -ffunction-sections
    -fdata-sections
)
add_link_options(
    -Wl,--gc-sections
    # The images stay small and byte-stable: newlib ships debug_info that -g0 alone
    # doesn't remove from the final link.
    -Wl,--strip-debug
)

# No debug information in the images.
set(CMAKE_C_FLAGS_RELEASE "-Os -g0" CACHE STRING "" FORCE)
set(CMAKE_ASM_FLAGS_RELEASE "-g0" CACHE STRING "" FORCE)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
