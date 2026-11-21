cmake_minimum_required(VERSION 3.25)
project(agent-bench C ASM)

# One ELF per (case, version): version 0 is the correct firmware, 1.. carry the bug the case describes.
# Soft-float, no libc: nothing here depends on a vendor library, so the same ELF loads on the twin and on QEMU.
include(${CMAKE_CURRENT_LIST_DIR}/cases.cmake)
set(CPU_FLAGS -mcpu=cortex-m4 -mthumb -mfloat-abi=soft)

foreach(spec IN LISTS AGENT_BENCH_CASES)
    string(REPLACE ":" ";" parts "${spec}")
    list(GET parts 0 case)
    list(GET parts 1 last)
    foreach(v RANGE 0 ${last})
        set(tgt ${case}_v${v})
        add_executable(${tgt} src/rt.c src/${case}.c)
        target_compile_definitions(${tgt} PRIVATE BUG=${v} CASE_NAME="${case}_v${v}")
        target_compile_options(${tgt} PRIVATE ${CPU_FLAGS} -O1 -ffreestanding -fno-builtin -Wall)
        target_link_options(${tgt} PRIVATE ${CPU_FLAGS} -nostdlib -nostartfiles
            -T${CMAKE_CURRENT_LIST_DIR}/ld/stm32f407.ld)
        target_link_libraries(${tgt} PRIVATE gcc)
        set_target_properties(${tgt} PROPERTIES SUFFIX ".elf")
    endforeach()
endforeach()
