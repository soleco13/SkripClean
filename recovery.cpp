// Проверяем, что это NTFS или Bitlocker
if (!check_volume_requirements(volume_letter)) {
    throw std::runtime_error("Volume is not NTFS or Bitlocker");
}

// Открываем NTFS Explorer
std::shared_ptr<NTFSExplorer> explorer = std::make_shared<NTFSExplorer>(vol); 