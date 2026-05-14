cmake_minimum_required(VERSION 3.22.1)
project(gbsplayer)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_CXX_STANDARD 20)

set(SAMEBOY_ROOT ${CMAKE_CURRENT_LIST_DIR}/../../../../../../vendor/sameboy)

add_library(
    gbsplayer
    SHARED
    native_bridge.cpp
    ${SAMEBOY_ROOT}/Core/apu.c
    ${SAMEBOY_ROOT}/Core/camera.c
    ${SAMEBOY_ROOT}/Core/display.c
    ${SAMEBOY_ROOT}/Core/gb.c
    ${SAMEBOY_ROOT}/Core/joypad.c
    ${SAMEBOY_ROOT}/Core/mbc.c
    ${SAMEBOY_ROOT}/Core/memory.c
    ${SAMEBOY_ROOT}/Core/printer.c
    ${SAMEBOY_ROOT}/Core/random.c
    ${SAMEBOY_ROOT}/Core/rumble.c
    ${SAMEBOY_ROOT}/Core/save_state.c
    ${SAMEBOY_ROOT}/Core/sgb.c
    ${SAMEBOY_ROOT}/Core/sm83_cpu.c
    ${SAMEBOY_ROOT}/Core/timing.c
    ${SAMEBOY_ROOT}/Core/workboy.c
)

target_include_directories(
    gbsplayer
    PRIVATE
    ${SAMEBOY_ROOT}/Core
)

target_compile_definitions(
    gbsplayer
    PRIVATE
    _GNU_SOURCE=1
    GB_INTERNAL=1
    GB_VERSION=\"1.0.2\"
    GB_DISABLE_DEBUGGER=1
    GB_DISABLE_CHEATS=1
    GB_DISABLE_CHEAT_SEARCH=1
    GB_DISABLE_REWIND=1
)

if(ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "x86_64")
    target_link_options(gbsplayer PRIVATE "-Wl,-z,max-page-size=16384")
endif()

target_link_libraries(
    gbsplayer
    android
    log
    m
)
