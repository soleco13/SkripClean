import os
import sys
import ctypes
import win32file
import wmi
from pathlib import Path
import recovery  # Импортируем Python-модуль recovery.pyd
import logging
import threading
import queue
import time

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Создаем очередь для перехвата вывода из C++
cpp_output_queue = queue.Queue()

def cpp_output_reader():
    """
    Читает вывод из C++ и перенаправляет его в Python logger
    """
    while True:
        try:
            line = cpp_output_queue.get(timeout=0.1)
            if line:
                logger.debug(f"C++: {line}")
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error in output reader: {e}")
            break

# Запускаем поток для чтения вывода
output_thread = threading.Thread(target=cpp_output_reader, daemon=True)
output_thread.start()

def cpp_logger(message):
    """
    Callback-функция для логирования из C++
    """
    cpp_output_queue.put(message)

# Устанавливаем callback для логирования
recovery.set_logger_callback(cpp_logger)

def is_admin():
    """
    Проверяет, запущен ли скрипт с правами администратора.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def get_disk_and_volume_info(drive_letter):
    """
    Получает информацию о физическом диске и томе для указанной буквы диска.
    
    Args:
        drive_letter (str): Буква диска (например, "C")
    
    Returns:
        tuple: (disk_index, volume_index)
    """
    try:
        logger.debug(f"Getting disk and volume info for drive {drive_letter}")
        
        # Проверяем права администратора
        if not is_admin():
            raise Exception("Для доступа к физическим дискам требуются права администратора")
            
        # Проверяем корректность буквы диска
        if not drive_letter or len(drive_letter) != 1 or not drive_letter.isalpha():
            raise Exception("Некорректная буква диска. Укажите одну букву (например, 'C')")
            
        # Формируем путь к диску
        drive_path = f"{drive_letter}:\\"
        
        # Проверяем тип диска
        drive_type = win32file.GetDriveType(drive_path)
        logger.debug(f"Drive type: {drive_type}")
        if drive_type != win32file.DRIVE_FIXED:
            raise Exception(f"Диск {drive_letter}: не является фиксированным диском")
            
        # Получаем информацию о физическом диске через WMI
        c = wmi.WMI()
        
        # Получаем логический диск
        logical_disk = None
        for disk in c.Win32_LogicalDisk(DeviceID=f"{drive_letter}:"):
            logical_disk = disk
            logger.debug(f"Found logical disk: {disk.DeviceID}, Size: {disk.Size}, FreeSpace: {disk.FreeSpace}")
            break
            
        if not logical_disk:
            raise Exception(f"Не удалось найти логический диск {drive_letter}:")
            
        # Получаем физический диск через цепочку зависимостей
        partition = None
        physical_disk = None
        
        # Логический диск -> Раздел
        for part in c.Win32_LogicalDiskToPartition():
            if part.Dependent.DeviceID == logical_disk.DeviceID:
                partition = part.Antecedent
                logger.debug(f"Found partition: {partition.DeviceID}")
                break
                
        if not partition:
            raise Exception(f"Не удалось найти раздел для диска {drive_letter}:")
            
        # Раздел -> Физический диск
        for disk in c.Win32_DiskDrive():
            for part in disk.associators("Win32_DiskDriveToDiskPartition"):
                if part.DeviceID == partition.DeviceID:
                    physical_disk = disk
                    logger.debug(f"Found physical disk: {disk.DeviceID}, Size: {disk.Size}")
                    break
            if physical_disk:
                break
                
        if not physical_disk:
            raise Exception(f"Не удалось найти физический диск для {drive_letter}:")
            
        # Получаем индекс физического диска из пути
        disk_path = physical_disk.DeviceID  # Например, "\\\\.\\PHYSICALDRIVE0"
        disk_index = int(disk_path.replace("\\\\.\\PHYSICALDRIVE", ""))
        logger.debug(f"Disk index: {disk_index}")
        
        # Проверяем доступ к физическому диску
        handle = win32file.CreateFile(
            f"\\\\.\\PhysicalDrive{disk_index}",
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None,
            win32file.OPEN_EXISTING,
            0,
            None
        )
        win32file.CloseHandle(handle)
        
        # Получаем все разделы диска, отсортированные по смещению
        partitions = []
        for part in physical_disk.associators("Win32_DiskDriveToDiskPartition"):
            try:
                # Получаем смещение раздела
                offset = int(part.StartingOffset or 0)
                # Получаем размер раздела
                size = int(part.Size or 0)
                # Добавляем информацию о разделе
                partitions.append({
                    'device_id': part.DeviceID,
                    'offset': offset,
                    'size': size
                })
                logger.debug(f"Found partition: {part.DeviceID}, Offset: {offset}, Size: {size}")
            except Exception as e:
                logger.warning(f"Error getting partition info: {e}")
                continue
                
        # Сортируем разделы по смещению
        partitions.sort(key=lambda x: x['offset'])
        
        # Ищем индекс нужного раздела
        volume_index = None
        for i, part in enumerate(partitions):
            if part['device_id'] == partition.DeviceID:
                volume_index = i
                logger.debug(f"Found volume index: {i}")
                break
                
        if volume_index is None:
            raise Exception(f"Не удалось определить номер тома для {drive_letter}:")
            
        # Увеличиваем volume_index на 1, так как в модуле recovery индексация начинается с 1
        volume_index += 1
            
        return disk_index, volume_index
        
    except Exception as e:
        logger.error(f"Error getting disk info: {str(e)}")
        raise Exception(f"Ошибка получения информации о диске: {str(e)}")

def scan_deleted_files(drive_letter, time_filter=""):
    """
    Сканирует удаленные файлы на указанном диске с применением фильтра по времени.
    
    Args:
        drive_letter (str): Буква диска (например, "C")
        time_filter (str): Фильтр по времени ("1h", "2h", "3h", "today" или пустая строка)
    
    Returns:
        list: Список найденных удаленных файлов
    """
    # Проверяем права администратора
    if not is_admin():
        raise Exception("Для сканирования удаленных файлов требуются права администратора")
    
    try:
        # Проверяем файловую систему диска и выводим информацию
        c = wmi.WMI()
        filesystem_info = None
        for disk in c.Win32_LogicalDisk(DeviceID=f"{drive_letter}:"):
            filesystem_info = disk.FileSystem
            logger.info(f"Диск {drive_letter}: обнаружена файловая система {disk.FileSystem}")
            if disk.FileSystem not in ["NTFS"]:
                raise Exception(f"Диск {drive_letter}: имеет неподдерживаемую файловую систему ({disk.FileSystem}). Поддерживается только NTFS.")
            break
            
        if not filesystem_info:
            raise Exception(f"Не удалось определить файловую систему диска {drive_letter}:")
            
        # Получаем индексы диска и тома для отладки
        try:
            disk_index, volume_index = get_disk_and_volume_info(drive_letter)
            logger.info(f"Получены индексы: disk_index={disk_index}, volume_index={volume_index}")
        except Exception as e:
            logger.error(f"Ошибка получения индексов диска: {e}")
            raise
            
        # Используем функцию из Python-модуля для сканирования
        logger.info(f"Начинаем сканирование диска {drive_letter}...")
        try:
            deleted_files = recovery.scan_deleted_files(drive_letter, time_filter)
            logger.info(f"Сканирование завершено, найдено файлов: {len(deleted_files) if deleted_files else 0}")
        except RuntimeError as e:
            if "Invalid NTFS" in str(e) or "MFT Record" in str(e):
                logger.error(f"Ошибка инициализации NTFS: {e}")
                raise Exception(f"Ошибка доступа к NTFS структурам на диске {drive_letter}: {e}")
            raise
        
        # Преобразуем результаты в нужный формат
        files = []
        for file_info in deleted_files:
            # Собираем полный путь из компонентов
            full_path = "/".join(file_info.path_components)
            
            file_data = {
                "inode": str(file_info.inode),
                "type": file_info.type,
                "size": str(file_info.size),
                "date": file_info.last_write_time,
                "path": full_path,
                "entropy": "0.00"  # Пока не используется
            }
            files.append(file_data)
        
        return files
        
    except Exception as e:
        logger.error(f"Произошла ошибка при сканировании: {str(e)}")
        raise Exception(f"Ошибка сканирования удаленных файлов: {str(e)}")

def recover_file(drive_letter, inode, output_path):
    """
    Восстанавливает удаленный файл.
    
    Args:
        drive_letter (str): Буква диска
        inode (int): Номер inode файла
        output_path (str): Путь для сохранения восстановленного файла
    
    Returns:
        bool: True если файл успешно восстановлен
    """
    # Проверяем права администратора
    if not is_admin():
        raise Exception("Для восстановления файлов требуются права администратора")
    
    try:
        # Получаем индексы диска и тома через функцию из модуля
        disk_index, volume_index = get_disk_and_volume_info(drive_letter)
        
        # Проверяем корректность inode
        if not isinstance(inode, (int, str)) or (isinstance(inode, str) and not inode.isdigit()):
            raise Exception("Некорректный номер inode")
        
        # Преобразуем inode в число
        inode_number = int(inode)
        
        # Используем функцию из Python-модуля для восстановления
        success = recovery.restore_file(inode_number, output_path, disk_index, volume_index)
        return success
        
    except Exception as e:
        raise Exception(f"Ошибка восстановления файла: {str(e)}")

def get_filesystem_type(drive_letter):
    try:
        logger.debug(f"Checking filesystem type for drive {drive_letter} using WMI")
        c = wmi.WMI()
        for logical_disk in c.Win32_LogicalDisk():
            logger.debug(f"Found disk: {logical_disk.DeviceID} - {logical_disk.FileSystem}")
            if logical_disk.DeviceID.lower() == f"{drive_letter.lower()}:":
                fs_type = logical_disk.FileSystem
                logger.info(f"Drive {drive_letter} filesystem type: {fs_type}")
                return fs_type
    except Exception as e:
        logger.error(f"WMI Error: {e}")
    return None

def is_system_drive(drive_letter):
    system_drive = os.environ.get('SystemDrive', 'C:').lower()
    return drive_letter.lower() + ':' == system_drive.lower()

def check_volume_requirements(volume_letter):
    logger.info(f"Checking volume requirements for {volume_letter}")
    
    # Проверяем, является ли это системным диском
    if is_system_drive(volume_letter):
        logger.info("Detected system drive")
        if not is_admin():
            logger.error("Admin rights required for system drive access")
            raise PermissionError("Требуются права администратора для доступа к системному диску")
            
    # Проверяем через WMI
    fs_type = get_filesystem_type(volume_letter)
    if fs_type and fs_type.upper() == "NTFS":
        logger.info(f"Volume {volume_letter} is NTFS (confirmed by WMI)")
        return True
        
    # Если WMI не сработал, пробуем стандартную проверку
    try:
        logger.debug(f"Falling back to standard volume check for {volume_letter}")
        vol = get_volume_by_letter(volume_letter)
        is_valid = vol.filesystem() in ["NTFS", "Bitlocker"]
        logger.info(f"Volume {volume_letter} filesystem: {vol.filesystem()}, is valid: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Volume check error: {e}")
        if is_system_drive(volume_letter):
            logger.info("Assuming system drive is NTFS")
            return True
        return False 