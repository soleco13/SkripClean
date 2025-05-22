#include "folder_search.hpp"
#include <filesystem>
#include <algorithm>
#include <thread>
#include <chrono>

namespace fs = std::filesystem;

uint64_t FolderSearch::getFolderSize(const std::string& folderPath) {
    uint64_t totalSize = 0;
    try {
        for (const auto& entry : fs::recursive_directory_iterator(
            folderPath,
            fs::directory_options::skip_permission_denied
        )) {
            if (fs::is_regular_file(entry) && !fs::is_symlink(entry)) {
                try {
                    totalSize += fs::file_size(entry);
                } catch (...) {
                    continue;
                }
            }
        }
    } catch (...) {
        return 0;
    }
    return totalSize;
}

bool FolderSearch::isExcluded(const std::string& path, const std::set<std::string>& excludeDirs) {
    fs::path fsPath(path);
    for (const auto& part : fsPath) {
        if (excludeDirs.find(part.string()) != excludeDirs.end()) {
            return true;
        }
    }
    return false;
}

uint64_t FolderSearch::countFolders(const std::string& rootPath, const std::set<std::string>& excludeDirs) {
    uint64_t total = 0;
    try {
        for (const auto& entry : fs::recursive_directory_iterator(
            rootPath,
            fs::directory_options::skip_permission_denied
        )) {
            if (fs::is_directory(entry) && !isExcluded(entry.path().string(), excludeDirs)) {
                total++;
            }
        }
    } catch (...) {}
    return total;
}

std::vector<FolderInfo> FolderSearch::findLargeFolders(
    const std::string& rootPath,
    uint64_t sizeThresholdMb,
    const std::set<std::string>& excludeDirs
) {
    std::vector<FolderInfo> largeFolders;
    uint64_t sizeThreshold = sizeThresholdMb * 1024 * 1024;
    
    try {
        // Сначала собираем список всех папок для сканирования
        std::vector<fs::path> dirsToScan;
        for (const auto& entry : fs::recursive_directory_iterator(
            rootPath,
            fs::directory_options::skip_permission_denied
        )) {
            if (fs::is_directory(entry) && !isExcluded(entry.path().string(), excludeDirs)) {
                dirsToScan.push_back(entry.path());
            }
        }
        
        // Теперь сканируем каждую папку с возможностью обновления прогресса
        size_t totalDirs = dirsToScan.size();
        for (size_t i = 0; i < totalDirs; ++i) {
            const auto& dir = dirsToScan[i];
            uint64_t size = getFolderSize(dir.string());
            if (size > sizeThreshold) {
                largeFolders.push_back({dir.string(), size});
            }
            
            // Каждые 10 папок делаем небольшую паузу, чтобы GUI мог обработать события
            if (i % 10 == 0) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
    } catch (...) {}

    std::sort(largeFolders.begin(), largeFolders.end(),
        [](const FolderInfo& a, const FolderInfo& b) {
            return a.size > b.size;
        });

    return largeFolders;
}
