cmake_minimum_required(VERSION 3.28)
project(BX_C0432_MSVC_OBJ LANGUAGES CXX)
add_library(bx_cached OBJECT ../bx_cached.cpp)
set_property(TARGET bx_cached PROPERTY CXX_STANDARD 17)
