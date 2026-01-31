"""
Prompt Manager - 管理 System Prompt 的載入與更新
支持熱重載：修改 Prompt 檔案後自動生效（開發環境）
"""
import os
from datetime import datetime


class PromptManager:
    def __init__(self, prompt_file='prompts/system_prompt.md'):
        self.prompt_file = prompt_file
        self.prompt_cache = None
        self.last_loaded = None
        
    def load_prompt(self, force_reload=False):
        """
        載入 System Prompt
        
        Args:
            force_reload: 強制重新載入（無視快取）
            
        Returns:
            str: System Prompt 內容，如果載入失敗則返回 None
        """
        # 取得完整路徑
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, self.prompt_file)
        
        try:
            # 檢查檔案是否存在
            if not os.path.exists(file_path):
                print(f"⚠️ Prompt 檔案不存在: {file_path}")
                return None
            
            # 檢查檔案修改時間（支持熱重載）
            file_mtime = os.path.getmtime(file_path)
            
            if force_reload or self.prompt_cache is None or file_mtime > (self.last_loaded or 0):
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.prompt_cache = f.read()
                self.last_loaded = file_mtime
                print(f"✅ System Prompt 已載入: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   檔案: {file_path}")
                print(f"   大小: {len(self.prompt_cache)} 字元")
            
            return self.prompt_cache
            
        except Exception as e:
            print(f"❌ 載入 Prompt 失敗: {e}")
            return None
    
    def backup_prompt(self, version=None):
        """
        備份當前 System Prompt
        
        Args:
            version: 版本號（預設：時間戳記）
            
        Returns:
            str: 備份檔案路徑，如果備份失敗則返回 None
        """
        if version is None:
            version = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source_file = os.path.join(base_dir, self.prompt_file)
        backup_file = os.path.join(base_dir, f'prompts/system_prompt_v{version}.md')
        
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Prompt 已備份: {backup_file}")
            return backup_file
            
        except Exception as e:
            print(f"❌ 備份失敗: {e}")
            return None
