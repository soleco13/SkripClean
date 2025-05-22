#pragma once

#include <string>
#include <vector>
#include <memory>
#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <map>
#include <set>
#include <chrono>
#include <thread>
#include <mutex>
#include <filesystem>

// Windows specific headers
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winioctl.h>
#include <tchar.h>
#endif

// Python headers
#include <Python.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h> 