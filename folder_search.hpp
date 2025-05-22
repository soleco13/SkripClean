#pragma once
#include <string>
#include <vector>
#include <set>
#include <utility>

struct FolderInfo {
    std::string path;
    uint64_t size;
};

class FolderSearch {
public:
    static uint64_t getFolderSize(const std::string& folderPath);
    static std::vector<FolderInfo> findLargeFolders(
        const std::string& rootPath,
        uint64_t sizeThresholdMb,
        const std::set<std::string>& excludeDirs
    );
    static bool isExcluded(const std::string& path, const std::set<std::string>& excludeDirs);
    static uint64_t countFolders(const std::string& rootPath, const std::set<std::string>& excludeDirs);
};
