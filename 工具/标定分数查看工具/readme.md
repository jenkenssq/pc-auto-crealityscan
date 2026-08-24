win运行方式
双击.exe文件即可，标定完点刷新按钮

mac运行方式
双击"标定分数查看工具.command"文件即可，标定完点刷新按钮

首次使用前需要赋予执行权限（只需一次，在终端执行）：
chmod +x "标定分数查看工具.command"

若提示缺少 tkinter，执行: brew install python-tk

mac打包成免安装app（目标Mac无需装Python）
1. 在任一Mac上，双击"build_mac.command"打包（首次chmod +x build_mac.command）
2. 生成 dist/标定分数查看工具.app，拷到其他Mac双击即用
3. 若提示"无法验证开发者"，目标Mac执行一次: xattr -cr "标定分数查看工具.app"
注意：Mac包必须在Mac上打包，无法从Windows交叉编译