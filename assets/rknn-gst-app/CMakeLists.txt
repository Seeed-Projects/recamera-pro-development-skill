cmake_minimum_required(VERSION 3.16)
project(recamera_rknn_gst LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_RPATH_USE_ORIGIN ON)

if(NOT DEFINED RECAMERA_RKNNRT OR NOT EXISTS "${RECAMERA_RKNNRT}")
  message(FATAL_ERROR "Set RECAMERA_RKNNRT to the local board-compatible librknnrt.so")
endif()
if(NOT DEFINED RECAMERA_RKNN_RUNTIME_DIR)
  set(RECAMERA_RKNN_RUNTIME_DIR "/oem/usr/lib")
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-app-1.0)
find_path(RKNN_INCLUDE_DIR rknn_api.h
  HINTS "${CMAKE_CURRENT_SOURCE_DIR}/include"
  REQUIRED)

add_executable(recamera_rknn_gst src/main.cpp)
target_include_directories(recamera_rknn_gst PRIVATE "${RKNN_INCLUDE_DIR}")
target_link_libraries(recamera_rknn_gst PRIVATE PkgConfig::GST "${RECAMERA_RKNNRT}")
target_link_options(recamera_rknn_gst PRIVATE
  "LINKER:-rpath,${RECAMERA_RKNN_RUNTIME_DIR}")
