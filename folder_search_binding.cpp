#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "folder_search.hpp"

namespace py = pybind11;

PYBIND11_MODULE(folder_search_cpp, m) {
    py::class_<FolderInfo>(m, "FolderInfo")
        .def(py::init<>())
        .def_readwrite("path", &FolderInfo::path)
        .def_readwrite("size", &FolderInfo::size);

    m.def("get_folder_size", &FolderSearch::getFolderSize, "Get size of a folder in bytes");
    m.def("find_large_folders", &FolderSearch::findLargeFolders, "Find large folders");
    m.def("is_excluded", &FolderSearch::isExcluded, "Check if path should be excluded");
    m.def("count_folders", &FolderSearch::countFolders, "Count total folders for progress bar");
}
