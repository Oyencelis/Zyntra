import os
import json
base = r'C:\Users\User\AppData\Roaming\Code\User\History'
for folder in os.listdir(base):
    folder_path = os.path.join(base, folder)
    if os.path.isdir(folder_path):
        entries_file = os.path.join(folder_path, 'entries.json')
        if os.path.exists(entries_file):
            try:
                with open(entries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    res = data.get('resource', '')
                    if 'Zyntra-main' in res and 'routes.py' in res:
                        print(f'FOUND MATCH: {folder}')
                        for entry in data.get('entries', []):
                            print(f"  {entry['id']}")
            except:
                pass
