#!/usr/bin/env python3
"""
DUET 字體可用性測試工具

功能：
1. 從後端獲取所有已安裝字體（TTF 格式）
2. 測試每個字體是否有前端可用的 JSON 格式
3. 輸出前後端都可用的字體清單
"""

import json
import urllib.request
import urllib.error
import time
import sys

# 後端 API
BACKEND_URL = "https://duet-backend-wlw8.onrender.com/list-fonts"

# 前端 JSON 字體 CDN 模板
FRONTEND_CDN_TEMPLATE = "https://esm.sh/@compai/font-{}/data/typefaces/normal-400.json"

def get_backend_fonts():
    """獲取後端所有已安裝字體（只保留字體家族名稱）"""
    print("📡 正在獲取後端字體清單...")
    
    try:
        with urllib.request.urlopen(BACKEND_URL, timeout=30) as response:
            data = json.loads(response.read().decode())
            raw_fonts = data.get('fonts', [])
            
            print(f"   原始項目數: {len(raw_fonts)}")
            
            # 提取純字體名稱（去除路徑和 style）
            font_families = set()
            for font_entry in raw_fonts:
                # 格式: "/path/to/font.ttf: Font Name:style=Style"
                # 或: "/path/to/font.ttf: Font Name"
                
                if ':' in font_entry:
                    # 分割路徑和字體資訊
                    parts = font_entry.split(': ', 1)
                    if len(parts) == 2:
                        font_info = parts[1]
                        
                        # 移除 style 資訊
                        if ':style=' in font_info:
                            font_name = font_info.split(':style=')[0].strip()
                        else:
                            font_name = font_info.strip()
                        
                        # 處理逗號分隔的多個名稱（某些字體有別名）
                        for name in font_name.split(','):
                            clean_name = name.strip()
                            if clean_name:
                                font_families.add(clean_name)
            
            fonts = sorted(font_families)
            print(f"✅ 後端共有 {len(fonts)} 個字體家族")
            
            # 顯示前 10 個（供確認）
            print(f"   前10個: {', '.join(fonts[:10])}")
            
            return fonts
    except Exception as e:
        print(f"❌ 獲取後端字體失敗: {e}")
        sys.exit(1)

def font_name_to_package_name(font_name):
    """將字體名稱轉換為 npm package 名稱格式"""
    # 例如: "Playfair Display" -> "playfair-display"
    return font_name.lower().replace(' ', '-')

def test_frontend_availability(font_name):
    """測試字體是否有前端可用的 JSON 格式"""
    package_name = font_name_to_package_name(font_name)
    url = FRONTEND_CDN_TEMPLATE.format(package_name)
    
    try:
        # 使用 HEAD 請求（只獲取 header，不下載內容）
        request = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except:
        return False

def categorize_fonts(fonts):
    """根據字體名稱特徵進行分類"""
    categories = {
        'serif': [],      # 襯線體
        'sans': [],       # 無襯線體
        'display': [],    # 展示體
        'handwriting': [], # 手寫體
        'monospace': [],  # 等寬字體
        'other': []       # 其他
    }
    
    # 簡單的關鍵字分類
    serif_keywords = ['Serif', 'Garamond', 'Baskerville', 'Times', 'Georgia', 'Playfair', 'Merriweather']
    sans_keywords = ['Sans', 'Roboto', 'Inter', 'Helvetica', 'Arial', 'Lato', 'Montserrat']
    display_keywords = ['Display', 'Fatface', 'Ultra', 'Black', 'Heavy']
    handwriting_keywords = ['Script', 'Handwriting', 'Brush', 'Casual', 'Cursive']
    monospace_keywords = ['Mono', 'Code', 'Courier', 'Console']
    
    for font in fonts:
        if any(kw in font for kw in monospace_keywords):
            categories['monospace'].append(font)
        elif any(kw in font for kw in handwriting_keywords):
            categories['handwriting'].append(font)
        elif any(kw in font for kw in display_keywords):
            categories['display'].append(font)
        elif any(kw in font for kw in serif_keywords):
            categories['serif'].append(font)
        elif any(kw in font for kw in sans_keywords):
            categories['sans'].append(font)
        else:
            categories['other'].append(font)
    
    return categories

def main():
    print("🔍 DUET 字體可用性測試工具")
    print("=" * 60)
    
    # 步驟 1: 獲取後端字體
    backend_fonts = get_backend_fonts()
    
    # 步驟 2: 測試前端可用性
    print(f"\n🧪 開始測試前端 JSON 可用性...")
    print(f"   （這可能需要 5-15 分鐘，請耐心等待）")
    
    available_fonts = []
    total = len(backend_fonts)
    
    for i, font_name in enumerate(backend_fonts, 1):
        # 顯示進度
        if i % 50 == 0 or i == total:
            print(f"   進度: {i}/{total} ({i*100//total}%)")
        
        if test_frontend_availability(font_name):
            available_fonts.append(font_name)
        
        # 避免請求過快
        time.sleep(0.05)
    
    # 步驟 3: 輸出結果
    print(f"\n✅ 測試完成！")
    print(f"   後端字體總數: {len(backend_fonts)}")
    print(f"   前端可用字體: {len(available_fonts)}")
    print(f"   不可用字體: {len(backend_fonts) - len(available_fonts)}")
    
    # 步驟 4: 分類
    print(f"\n📊 字體分類:")
    categories = categorize_fonts(available_fonts)
    for cat_name, cat_fonts in categories.items():
        if cat_fonts:
            print(f"   {cat_name}: {len(cat_fonts)} 種")
    
    # 步驟 5: 保存結果
    output_file = 'available-fonts.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(available_fonts),
            'fonts': available_fonts,
            'categories': categories
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 結果已保存到: {output_file}")
    
    # 步驟 6: 顯示前 20 個可用字體（供確認）
    print(f"\n📋 前 20 個可用字體:")
    for i, font in enumerate(available_fonts[:20], 1):
        print(f"   {i}. {font}")
    
    print(f"\n✅ 完成！請將 {output_file} 提供給 Claude 進行精選。")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 測試已中斷")
        sys.exit(1)
