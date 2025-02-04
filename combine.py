import json
import os

# 合併資料夾內的所有 json 至一個 json
FOLDER_LIST = ["buses", "maps", "newsletters"]


def combine_json_files(path, folder_list):
    for folder in folder_list:
        combined_data = {}
        folder_path = os.path.join(path, folder)
        for file in os.listdir(folder_path):
            if file.endswith(".json"):
                with open(os.path.join(folder_path, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 移除檔名的 .json
                    combined_data[file[:-5]] = data
        file_path = os.path.join(path, folder)
        with open(os.path.join(file_path + ".json"), "w", encoding="utf-8") as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)
        print(f"{folder}.json 已合併！")


combine_json_files("json", FOLDER_LIST)
