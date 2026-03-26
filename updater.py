#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaTrade Pro - 自动更新模块
支持检查更新、下载、半自动安装
"""

import os
import sys
import json
import time
import zipfile
import requests
import subprocess
from pathlib import Path
from typing import Optional, Callable


class Updater:
    """
    自动更新器
    
    更新流程：
    1. 检查服务器版本
    2. 对比本地版本
    3. 下载新版本 ZIP
    4. 解压到 update/ 目录
    5. 提示用户运行 update.bat 完成替换
    """
    
    # 版本信息地址
    VERSION_URL = "http://8.217.13.0:18080/aquatrade/version.json"
    DOWNLOAD_URL = "http://8.217.13.0:18080/aquatrade/AquaTrade-Pro-v{version}.zip"
    
    def __init__(self, current_version: str = "1.1.6", progress_callback: Callable = None):
        self.current_version = current_version
        self.progress_callback = progress_callback
        self.update_dir = Path(__file__).parent / "update"
        self.version_info = None
        
    def check_update(self) -> dict:
        """
        检查是否有新版本
        
        Returns:
            {
                'has_update': bool,
                'latest_version': str,
                'current_version': str,
                'changelog': str,
                'download_url': str
            }
        """
        try:
            # 从服务器获取版本信息
            response = requests.get(self.VERSION_URL, timeout=10)
            response.raise_for_status()
            
            self.version_info = response.json()
            latest_version = self.version_info.get('version', '1.0.0')
            
            # 比较版本号
            has_update = self._compare_version(latest_version, self.current_version) > 0
            
            return {
                'has_update': has_update,
                'latest_version': latest_version,
                'current_version': self.current_version,
                'changelog': self.version_info.get('changelog', ''),
                'download_url': self.version_info.get('download_url', '')
            }
            
        except requests.exceptions.ConnectionError:
            return {
                'has_update': False,
                'error': '无法连接到更新服务器，请检查网络'
            }
        except Exception as e:
            return {
                'has_update': False,
                'error': f'检查更新失败: {str(e)}'
            }
    
    def _compare_version(self, v1: str, v2: str) -> int:
        """比较版本号，v1>v2返回1，v1<v2返回-1，相等返回0"""
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        
        for i in range(max(len(parts1), len(parts2))):
            p1 = parts1[i] if i < len(parts1) else 0
            p2 = parts2[i] if i < len(parts2) else 0
            if p1 > p2:
                return 1
            elif p1 < p2:
                return -1
        return 0
    
    def download_update(self, download_url: str = None, version: str = None) -> dict:
        """
        下载更新包
        
        Returns:
            {
                'success': bool,
                'message': str,
                'file_path': str  # 下载的文件路径
            }
        """
        if download_url is None:
            # 如果 version_info 不存在，使用传入的 version 或默认值
            ver = version or (self.version_info.get('version', 'latest') if self.version_info else 'latest')
            download_url = self.DOWNLOAD_URL.format(version=ver)
        
        try:
            # 创建更新目录
            self.update_dir.mkdir(exist_ok=True)
            
            # 下载文件
            zip_path = self.update_dir / "update.zip"
            
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 回调进度
                        if self.progress_callback and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_callback(progress)
            
            # 解压
            self._extract_update(zip_path)
            
            # 创建更新脚本
            self._create_update_script()
            
            return {
                'success': True,
                'message': '更新包下载完成',
                'file_path': str(zip_path)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'下载失败: {str(e)}'
            }
    
    def _extract_update(self, zip_path: Path):
        """解压更新包"""
        extract_dir = self.update_dir / "new_version"
        extract_dir.mkdir(exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        print(f"[Updater] 已解压到: {extract_dir}")
    
    def _create_update_script(self):
        """创建更新脚本（Windows bat）"""
        app_dir = Path(__file__).parent
        update_script = app_dir / "run_update.bat"
        
        bat_content = '''@echo off
chcp 65001 >nul
title AquaTrade Pro 更新程序
echo ==========================================
echo      AquaTrade Pro 更新程序
echo ==========================================
echo.
echo 正在关闭 AquaTrade Pro...
taskkill /F /IM AquaTrade.exe 2>nul
timeout /T 2 /NOBREAK >nul

echo 正在备份配置...
if exist config.json copy config.json config.json.backup
echo 备份完成

echo 正在复制新文件...
xcopy /E /Y /Q "update\\new_version\\*" ".\" 
echo 文件复制完成

echo 正在清理临时文件...
rmdir /S /Q update
echo 清理完成

echo.
echo ==========================================
echo      更新完成！正在启动新版本...
echo ==========================================
timeout /T 2 /NOBREAK >nul
start "" "AquaTrade.exe"
del "%~f0"
'''
        
        with open(update_script, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        
        print(f"[Updater] 已创建更新脚本: {update_script}")
    
    def apply_update(self) -> dict:
        """
        应用更新（关闭程序并运行更新脚本）
        
        注意：这会关闭当前程序！
        """
        app_dir = Path(__file__).parent
        update_script = app_dir / "run_update.bat"
        
        if not update_script.exists():
            return {
                'success': False,
                'message': '更新脚本不存在，请重新下载更新'
            }
        
        try:
            # 启动更新脚本（独立进程）
            subprocess.Popen(
                [str(update_script)],
                cwd=str(app_dir),
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            return {
                'success': True,
                'message': '更新程序已启动，即将关闭当前程序'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'启动更新失败: {str(e)}'
            }


class UpdateChecker:
    """
    启动时自动检查更新（非阻塞）
    """
    
    def __init__(self, current_version: str = "1.1.1"):
        self.current_version = current_version
        self.updater = Updater(current_version)
        self.last_check_file = Path(__file__).parent / ".last_update_check"
        
    def should_check(self) -> bool:
        """是否应该检查更新（每天一次）"""
        if not self.last_check_file.exists():
            return True
        
        try:
            last_check = float(self.last_check_file.read_text().strip())
            # 如果超过24小时
            return (time.time() - last_check) > 86400
        except:
            return True
    
    def mark_checked(self):
        """标记已检查"""
        self.last_check_file.write_text(str(time.time()))
    
    def check_silently(self) -> Optional[dict]:
        """静默检查更新，返回结果但不弹窗"""
        if not self.should_check():
            return None
        
        result = self.updater.check_update()
        self.mark_checked()
        
        return result if result.get('has_update') else None


# 本地版本信息文件（用于测试）
def create_local_version_file(version: str = "1.1.1"):
    """创建本地版本信息文件（如果服务器不可用）"""
    version_file = Path(__file__).parent / "version.json"
    
    info = {
        "version": version,
        "build_date": time.strftime("%Y-%m-%d"),
        "changelog": "当前版本"
    }
    
    with open(version_file, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2)
    
    return version_file


if __name__ == '__main__':
    # 测试
    updater = Updater("1.0.0")
    
    print("检查更新...")
    result = updater.check_update()
    print(f"结果: {result}")
    
    if result.get('has_update'):
        print(f"发现新版本: {result['latest_version']}")
        print(f"更新内容: {result['changelog']}")
