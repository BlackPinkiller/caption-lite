cmake_minimum_required(VERSION 3.31.6)

project("hy-mt2" LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED true)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED true)

if(DEFINED ANDROID_ABI)
    if(ANDROID_ABI STREQUAL "arm64-v8a")
        set(GGML_SYSTEM_ARCH "ARM")
    else()
        message(FATAL_ERROR "HyMT2 (STQ1_0) requires arm64-v8a")
    endif()
endif()

set(LLAMA_SRC ${CMAKE_CURRENT_LIST_DIR}/../../../llama-cpp)
add_subdirectory(${LLAMA_SRC} build-llama)

add_library(hy_mt2 SHARED hy_mt2_jni.cpp)

target_include_directories(hy_mt2 PRIVATE
        ${LLAMA_SRC}
        ${LLAMA_SRC}/common
        ${LLAMA_SRC}/include
        ${LLAMA_SRC}/ggml/include
        ${LLAMA_SRC}/ggml/src)

target_link_libraries(hy_mt2
        llama
        llama-common
        android
        log)
