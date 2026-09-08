# Git 版本管理说明

## 当前状态
✅ Git 仓库已初始化
✅ 当前版本已提交为初始版本

## 提交信息
```
commit 87af91a
Initial commit: 固件升级自动化测试框架基础版本
```

## 常用 Git 命令

### 查看状态
```bash
cd D:\固件升级自动化
git status
```

### 查看修改内容
```bash
# 查看未暂存的修改
git diff

# 查看已暂存的修改
git diff --staged
```

### 提交修改
```bash
# 添加所有修改
git add -A

# 提交
git commit -m "描述你的修改"
```

### 查看历史
```bash
# 查看提交历史
git log --oneline

# 查看详细历史
git log
```

### 回滚修改

#### 回滚未提交的修改
```bash
# 回滚单个文件
git checkout -- core/firmware_handler.py

# 回滚所有文件
git checkout -- .
```

#### 回滚到上一个提交
```bash
# 保留修改，只撤销提交
git reset --soft HEAD^

# 撤销提交和暂存，保留修改
git reset HEAD^

# 完全撤销，丢弃所有修改（危险！）
git reset --hard HEAD^
```

#### 回滚到指定提交
```bash
# 查看提交历史，找到 commit ID
git log --oneline

# 回滚到指定提交
git reset --hard <commit-id>
```

### 查看某个文件的历史版本
```bash
# 查看文件的修改历史
git log -- core/firmware_handler.py

# 查看某个提交的文件内容
git show <commit-id>:core/firmware_handler.py
```

### 创建分支（可选）
```bash
# 创建并切换到新分支
git checkout -b feature/upgrade-confirm-fix

# 切换回主分支
git checkout master

# 合并分支
git merge feature/upgrade-confirm-fix
```

## 建议的工作流程

### 每次修改前
```bash
# 1. 查看当前状态
git status

# 2. 如果有未提交的修改，先提交
git add -A
git commit -m "描述当前状态"
```

### 修改后
```bash
# 1. 查看修改了什么
git diff

# 2. 如果满意，提交
git add -A
git commit -m "描述你的修改"

# 3. 如果不满意，回滚
git checkout -- .
```

## .gitignore 配置

已配置忽略以下文件：
- `logs/` - 测试日志
- `screenshots/` - 截图
- `__pycache__/` - Python 缓存
- `*.log` - 日志文件
- `resources/firmware/*.zip` - 固件文件

## 下次修改前的操作

在进行任何修改之前，运行：
```bash
cd D:\固件升级自动化
git add -A
git commit -m "修改前备份: <描述当前状态>"
```

这样就可以随时回滚到修改前的状态。

## 快速回滚到初始版本

如果需要回滚到当前的初始版本：
```bash
cd D:\固件升级自动化
git reset --hard 87af91a
```

## 注意事项

1. **提交前先测试**：确保代码能运行再提交
2. **写清楚提交信息**：方便以后查找
3. **定期提交**：不要积累太多修改
4. **谨慎使用 --hard**：会丢失所有未提交的修改
