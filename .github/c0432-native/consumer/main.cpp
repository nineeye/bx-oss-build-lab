#include <iostream>
extern "C" int bx_c0432_cached_value();
int main() { int v=bx_c0432_cached_value(); if(v!=4321) return 3; std::cout << "BX_C0432_CROSS_RUNNER_PASS " << v << "\n"; return 0; }
