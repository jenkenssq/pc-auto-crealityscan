"""
邮件发送模块
用于发送测试报告邮件
"""

import smtplib
import os
import sys
import base64
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email import encoders
from typing import List, Optional


class EmailSender:
    """邮件发送器"""

    # 阿里邮箱默认SMTP配置
    DEFAULT_SMTP_SERVER = "smtp.aliyun.com"
    DEFAULT_SMTP_PORT_SSL = 465
    DEFAULT_SMTP_PORT_TLS = 587

    def __init__(self, smtp_server: str = None, smtp_port: int = None,
                 sender_email: str = None, sender_password: str = None,
                 use_ssl: bool = True):
        """
        初始化邮件发送器

        Args:
            smtp_server: SMTP服务器地址
            smtp_port: SMTP端口
            sender_email: 发件人邮箱
            sender_password: 发件人密码或授权码
            use_ssl: 是否使用SSL（默认True，端口465用SSL，端口587用TLS）
        """
        self.smtp_server = smtp_server or self.DEFAULT_SMTP_SERVER
        self.smtp_port = smtp_port or (self.DEFAULT_SMTP_PORT_SSL if use_ssl else self.DEFAULT_SMTP_PORT_TLS)
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.use_ssl = use_ssl

    def send_report(self, recipients: List[str], report_path: str,
                    subject: str = "CrealityScan测试报告",
                    body: str = "测试完成，请查看附件报告。") -> bool:
        """
        发送测试报告邮件（HTML格式，内嵌图片）

        Args:
            recipients: 收件人列表
            report_path: 报告文件路径
            subject: 邮件主题
            body: 邮件正文

        Returns:
            bool: 是否发送成功
        """
        if not self.sender_email or not self.sender_password:
            raise ValueError("发件人邮箱和密码不能为空")

        if not recipients:
            raise ValueError("收件人列表不能为空")

        msg = MIMEMultipart('mixed')
        msg['From'] = self.sender_email
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject

        # 准备HTML内容和内嵌图片
        html_content = body
        image_cids = {}

        if report_path and os.path.exists(report_path):
            try:
                report_dir = Path(report_path).parent

                # 读取HTML报告内容
                with open(report_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                # 处理内嵌图片（screenshots和charts）
                for folder in ['screenshots', 'charts']:
                    folder_path = report_dir / folder
                    if folder_path.exists():
                        for img_file in folder_path.glob('*'):
                            if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
                                # 读取图片
                                with open(img_file, 'rb') as f:
                                    img_data = f.read()

                                # 创建MIMEImage
                                img_mime = MIMEImage(img_data)
                                img_name = img_file.name

                                # 生成唯一的Content-ID，使用文件夹前缀避免冲突
                                cid = f"{folder}_{img_name}"
                                img_mime.add_header('Content-ID', f'<{cid}>')
                                img_mime.add_header('Content-Disposition', 'inline', filename=img_name)

                                msg.attach(img_mime)

                                # 替换HTML中的图片路径为CID引用
                                # 例如: screenshots/xxx.png -> cid:screenshots_xxx.png
                                full_path = f'{folder}/{img_name}'
                                html_content = html_content.replace(
                                    full_path,
                                    f'cid:{cid}'
                                )
                                # 也处理反斜杠
                                html_content = html_content.replace(
                                    f'{folder}\\{img_name}',
                                    f'cid:{cid}'
                                )

                print(f"处理后的HTML内容包含的cid: {image_cids}")

            except Exception as e:
                print(f"处理报告图片失败: {e}")

        # 创建HTML邮件部分
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)

        # 发送邮件
        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)

            print(f"邮件发送成功: {recipients}")
            return True

        except smtplib.SMTPAuthenticationError:
            print("邮件发送失败: 用户名或密码错误")
            raise
        except smtplib.SMTPException as e:
            print(f"邮件发送失败: {e}")
            raise

    def test_connection(self, recipients: List[str]) -> bool:
        """
        测试邮件发送功能（发送测试邮件）

        Args:
            recipients: 收件人列表

        Returns:
            bool: 是否发送成功
        """
        try:
            return self.send_report(
                recipients=recipients,
                report_path=None,
                subject="[测试] CrealityScan测试工具邮件配置验证",
                body="""<html>
<body>
    <h2>邮件配置验证</h2>
    <p>这是一封测试邮件，用于验证邮件配置是否正确。</p>
    <p>如果收到此邮件，说明配置正常。</p>
</body>
</html>"""
            )
        except Exception as e:
            print(f"测试邮件发送失败: {e}")
            return False


def create_email_sender_from_config(config: dict = None) -> EmailSender:
    """
    从配置创建邮件发送器

    Args:
        config: 配置字典，包含 smtp_server, smtp_port, sender_email, sender_password

    Returns:
        EmailSender实例
    """
    # 兼容打包和源码运行
    if config is None:
        config = {}

    # 从配置文件加载（如果存在）
    settings_file = None
    if getattr(sys, 'frozen', False):
        settings_file = Path(sys.executable).parent / "settings.json"
    else:
        settings_file = Path(__file__).parent.parent / "settings.json"

    if settings_file.exists():
        import json
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                config.update({
                    k: v for k, v in settings.items()
                    if k in ['smtp_server', 'smtp_port', 'sender_email', 'sender_password']
                })
        except Exception:
            pass

    return EmailSender(
        smtp_server=config.get('smtp_server'),
        smtp_port=config.get('smtp_port'),
        sender_email=config.get('sender_email'),
        sender_password=config.get('sender_password'),
        use_ssl=config.get('use_ssl', True)
    )


if __name__ == "__main__":
    # 测试邮件发送功能
    import argparse

    parser = argparse.ArgumentParser(description='邮件发送测试')
    parser.add_argument('--to', required=True, help='收件人邮箱')
    parser.add_argument('--from', dest='sender', required=True, help='发件人邮箱')
    parser.add_argument('--password', required=True, help='发件人密码或授权码')
    parser.add_argument('--smtp', default='smtp.aliyun.com', help='SMTP服务器')
    parser.add_argument('--port', type=int, default=465, help='SMTP端口')

    args = parser.parse_args()

    sender = EmailSender(
        smtp_server=args.smtp,
        smtp_port=args.port,
        sender_email=args.sender,
        sender_password=args.password,
        use_ssl=(args.port == 465)
    )

    result = sender.test_connection([args.to])
    print(f"测试{'成功' if result else '失败'}")