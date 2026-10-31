from repository import Repository

if __name__ == "__main__":
    repo = Repository()
    repo.initialize()
    print(f"数据库已初始化（保留已有数据）：{repo.settings.db_path}")
