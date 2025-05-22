cmake_minimum_required(VERSION 3.15)
project(FolderSearch)

# Используем C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Настройка компилятора MSVC
if(MSVC)
    add_compile_options(
        /MP         # Многопоточность
        /W4         # Все предупреждения
        /wd4251     # DLL interface warning
        /wd4996     # Deprecated функции
    )
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /NODEFAULTLIB:MSVCRTD")
endif()

# Указываем путь к pybind11
set(pybind11_DIR "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Lib/site-packages/pybind11/share/cmake/pybind11")

# Находим Python и pybind11
find_package(Python COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

# Явно указываем исходные файлы для модуля folder_search_cpp
set(SOURCES
    folder_search.cpp
    folder_search_binding.cpp
)

# Создаем модуль folder_search_cpp
pybind11_add_module(folder_search_cpp ${SOURCES})

# Настраиваем include директории для folder_search_cpp
target_include_directories(folder_search_cpp PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${Python_INCLUDE_DIRS}
)

# Устанавливаем выходную директорию
set_target_properties(folder_search_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)
