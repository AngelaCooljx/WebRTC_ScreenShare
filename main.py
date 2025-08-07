from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import json
import os
import sys
import subprocess
import threading
import socket
import struct
import asyncio
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime
import ipaddress

# 全局变量
server_process = None
server_thread = None
shutdown_event = threading.Event()
cert_file = "cert.pem"
key_file = "key.pem"


def get_local_ip():
    """获取本机IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"


def generate_certificate(key_path, cert_path):
    """生成自签名证书"""
    try:
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048)
        local_ip = get_local_ip()

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.UTC)
        ).not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3650)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ipaddress.IPv4Address(local_ip)),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return True
    except Exception:
        return False


class ScreenShareGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("局域网在线投屏")
        self.root.geometry("260x240")
        self.root.resizable(False, False)

        # 设置窗口图标
        try:
            # 获取程序所在目录
            if hasattr(sys, '_MEIPASS'):
                # 打包后的临时目录
                icon_path = os.path.join(sys._MEIPASS, "icon.ico")
            else:
                # 开发环境
                icon_path = "icon.ico"
            self.root.iconbitmap(icon_path)
        except:
            pass  # 如果图标文件不存在就忽略

        # 创建按钮
        ttk.Button(self.root, text="启动服务",
                   command=self.start_server, width=20).pack(pady=5)
        ttk.Button(self.root, text="停止服务",
                   command=self.stop_server, width=20).pack(pady=5)
        ttk.Button(self.root, text="指定证书和密钥",
                   command=self.select_cert, width=20).pack(pady=5)
        ttk.Button(self.root, text="生成自签名证书",
                   command=self.generate_cert, width=20).pack(pady=5)
        ttk.Button(self.root, text="访问投屏页面",
                   command=self.open_browser, width=20).pack(pady=5)
        ttk.Button(self.root, text="关于", command=self.show_about,
                   width=20).pack(pady=5)

    def start_server(self):
        global server_thread, shutdown_event
        if server_thread and server_thread.is_alive():
            messagebox.showwarning("警告", "服务已在运行")
            return

        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            messagebox.showerror("错误", "证书文件不存在，请先生成或指定证书")
            return

        shutdown_event.clear()
        server_thread = threading.Thread(target=self.run_server, daemon=True)
        server_thread.start()

        # 启动后自动打开浏览器
        threading.Timer(2.0, self.open_browser).start()

    def run_server(self):
        try:
            # 启动HTTP重定向服务器
            http_app = FastAPI()

            @http_app.get("/{path:path}")
            async def redirect_all(request: Request):
                host = request.headers.get("host", "localhost").split(":")[0]
                return RedirectResponse(url=f"https://{host}:443{request.url.path}", status_code=301)

            http_thread = threading.Thread(
                target=lambda: uvicorn.run(
                    http_app, host="0.0.0.0", port=80, log_level="critical", access_log=False, log_config=None),
                daemon=True
            )
            http_thread.start()

            # 启动STUN服务器
            stun_server = SimpleSTUNServer()
            stun_thread = threading.Thread(
                target=stun_server.start, daemon=True)
            stun_thread.start()

            # 启动HTTPS服务器
            uvicorn.run(
                app,
                host="0.0.0.0",
                port=443,
                log_level="critical",
                ssl_keyfile=key_file,
                ssl_certfile=cert_file,
                access_log=False,
                log_config=None
            )
        except Exception as e:
            messagebox.showerror("错误", f"服务启动失败: {e}")

    def stop_server(self):
        global server_thread, shutdown_event
        shutdown_event.set()
        if server_thread:
            # 强制终止当前进程来停止服务器
            os._exit(0)

    def select_cert(self):
        global cert_file, key_file
        key_path = filedialog.askopenfilename(
            title="选择私钥（key.pem）文件",
            initialdir=os.getcwd(),
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")]
        )
        if not key_path:
            return

        cert_path = filedialog.askopenfilename(
            title="选择证书（cert.pem）文件",
            initialdir=os.getcwd(),
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")]
        )
        if not cert_path:
            return

        key_file = key_path
        cert_file = cert_path
        messagebox.showinfo("成功", "证书和密钥已设置")

    def generate_cert(self):
        key_path = filedialog.asksaveasfilename(
            title="保存私钥（key.pem）文件",
            initialdir=os.getcwd(),
            defaultextension=".pem",
            initialfile="key.pem",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")]
        )
        if not key_path:
            return

        cert_path = filedialog.asksaveasfilename(
            title="保存证书（cert.pem）文件",
            initialdir=os.getcwd(),
            defaultextension=".pem",
            initialfile="cert.pem",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")]
        )
        if not cert_path:
            return

        if generate_certificate(key_path, cert_path):
            global cert_file, key_file
            cert_file = cert_path
            key_file = key_path
            messagebox.showinfo("成功", "证书生成完成")
        else:
            messagebox.showerror("错误", "证书生成失败")

    def open_browser(self):
        local_ip = get_local_ip()
        url = f"https://{local_ip}"
        webbrowser.open(url)

    def show_about(self):
        about_text = """WebRTC投屏工具

使用说明：
1. 首次使用请先指定证书和密钥文件，或生成自签名证书
2. 点击启动服务开始投屏服务
3. 在其他设备浏览器访问本机IP地址
4. 选择要投屏的屏幕或窗口

https://github.com/AngelaCooljx/WebRTC_ScreenShare"""
        messagebox.showinfo("关于", about_text)

    def run(self):
        self.root.mainloop()


# 全局变量用于控制服务器状态
shutdown_event = threading.Event()


# 简单的STUN服务器实现
class SimpleSTUNServer:
    def __init__(self, host='0.0.0.0', port=3478):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False

    def start(self):
        """启动STUN服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.host, self.port))
            self.running = True

            print(f"STUN服务器启动在 {self.host}:{self.port}")

            while self.running and not shutdown_event.is_set():
                try:
                    self.socket.settimeout(1.0)  # 设置超时，以便检查shutdown_event
                    data, addr = self.socket.recvfrom(1024)

                    # 简单的STUN响应处理
                    if len(data) >= 20:  # STUN消息最小长度
                        response = self.create_stun_response(data, addr)
                        if response:
                            self.socket.sendto(response, addr)

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"STUN服务器错误: {e}")
                    break

        except Exception as e:
            print(f"STUN服务器启动失败: {e}")
        finally:
            if self.socket:
                self.socket.close()

    def create_stun_response(self, request_data, client_addr):
        """创建STUN响应"""
        try:
            # 解析STUN请求头
            if len(request_data) < 20:
                return None

            msg_type, msg_length, magic_cookie = struct.unpack(
                '!HHI', request_data[:8])
            transaction_id = request_data[8:20]

            # 检查是否是STUN绑定请求
            if msg_type == 0x0001 and magic_cookie == 0x2112A442:
                # 创建成功响应
                response_type = 0x0101  # Binding Success Response

                # 创建XOR-MAPPED-ADDRESS属性
                ip_bytes = socket.inet_aton(client_addr[0])
                port = client_addr[1]

                # XOR映射的IP和端口
                xor_port = port ^ (magic_cookie >> 16)
                xor_ip = struct.unpack('!I', ip_bytes)[0] ^ magic_cookie

                # 构建属性
                attr_type = 0x0020  # XOR-MAPPED-ADDRESS
                attr_length = 8
                attr_value = struct.pack(
                    '!BBHI', 0, 1, xor_port, xor_ip)  # IPv4

                # 构建完整响应
                total_length = attr_length + 4  # 属性头 + 属性值
                response = struct.pack(
                    '!HHI', response_type, total_length, magic_cookie)
                response += transaction_id
                response += struct.pack('!HH', attr_type, attr_length)
                response += attr_value

                return response

        except Exception as e:
            print(f"创建STUN响应失败: {e}")

        return None

    def stop(self):
        """停止STUN服务器"""
        self.running = False


app = FastAPI(title="局域网在线投屏")


# 连接管理器
class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: str, sender: WebSocket = None):
        """广播消息给除发送者外的所有连接"""
        disconnected = []
        for connection in self.connections:
            if connection != sender:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get():
    """主页面"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>局域网在线投屏</title>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f6fa;
                min-height: 100vh;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 30px;
                font-size: 2.5em;
            }
            .status {
                padding: 15px;
                border-radius: 10px;
                font-weight: bold;
                flex: 1;
                margin-right: 10px;
            }
            .status.connected {
                background: #d4edda;
                color: #155724;
            }
            .status.disconnected {
                background: #f8d7da;
                color: #721c24;
            }
            .status-row {
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                gap: 10px;
            }
            .user-count {
                background: #e3f2fd;
                color: #1565c0;
                padding: 15px;
                border-radius: 10px;
                font-weight: bold;
                white-space: nowrap;
            }
            .controls {
                text-align: center;
                margin: 30px 0;
            }
            button {
                background: linear-gradient(45deg, #4CAF50, #45a049);
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 25px;
                cursor: pointer;
                font-size: 16px;
                margin: 10px;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0,0,0,0.3);
            }
            button:disabled {
                background: #ccc;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            .stop-btn {
                background: linear-gradient(45deg, #f44336, #da190b);
            }
            .info {
                background: #e9ecef;
                padding: 10px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: center;
            }
            .video-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-top: 30px;
            }
            .video-item {
                text-align: center;
                position: relative;
            }
            .video-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .video-label {
                font-weight: bold;
                font-size: 18px;
                color: #555;
            }
            video {
                width: 100%;
                max-width: 400px;
                height: 250px;
                border: 3px solid #ddd;
                border-radius: 10px;
                background: #000;
                object-fit: contain;
            }
            video:fullscreen {
                object-fit: contain;
                width: 100vw;
                height: 100vh;
                max-width: none;
                border: none;
                border-radius: 0;
            }
            video:-webkit-full-screen {
                object-fit: contain;
                width: 100vw;
                height: 100vh;
                max-width: none;
                border: none;
                border-radius: 0;
            }
            video:-moz-full-screen {
                object-fit: contain;
                width: 100vw;
                height: 100vh;
                max-width: none;
                border: none;
                border-radius: 0;
            }
            .empty-video {
                width: 100%;
                max-width: 400px;
                height: 250px;
                border: 3px dashed #ccc;
                border-radius: 10px;
                background: #f8f9fa;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #6c757d;
                font-size: 16px;
            }
            @media (max-width: 768px) {
                .video-grid {
                    grid-template-columns: 1fr;
                }
                .container {
                    padding: 20px;
                    margin: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🖥️ 局域网在线投屏</h1>
            
            <div class="status-row">
                <div id="status" class="status disconnected">
                    连接状态: 未连接
                </div>
                <div class="user-count">
                    在线用户: <span id="userCount">1</span> 人
                </div>
            </div>
            
            <div class="info">
                <p><strong>使用说明:</strong> 请将投屏端与展示端（服务端）连接至相同局域网；在投屏端使用浏览器访问当前页面地址栏相同网址，点击下方"开始投屏"，选择"整个屏幕"窗口进行共享。展示端投屏画面内可点击全屏。</p>
            </div>
            
            <div class="controls">
                <button id="shareBtn" onclick="toggleShare()">开始投屏</button>
                <button onclick="location.reload()">刷新页面</button>
            </div>
            
            <div class="video-grid">
                <div class="video-item">
                    <div class="video-header">
                        <div class="video-label">我的屏幕</div>
                    </div>
                    <video id="localVideo" autoplay muted controls style="display:none;"></video>
                    <div id="localPlaceholder" class="empty-video">等待开始投屏...</div>
                </div>
                <div class="video-item">
                    <div class="video-header">
                        <div class="video-label">投屏画面</div>
                    </div>
                    <video id="remoteVideo" autoplay controls style="display:none;"></video>
                    <div id="remotePlaceholder" class="empty-video">等待对方投屏...</div>
                </div>
            </div>
        </div>

        <script>
            let localStream = null;
            let peerConnection = null;
            let websocket = null;
            let isSharing = false;
            let myClientId = null;

            // WebRTC 配置
            const rtcConfig = {
                iceServers: [
                    { urls: `stun:${location.hostname}:3478` },  // 使用本机STUN服务器
                    { urls: 'stun:stun.l.google.com:19302' },   // 备用公网STUN
                    { urls: 'stun:stun1.l.google.com:19302' }   // 备用公网STUN
                ]
            };

            // 初始化
            window.onload = function() {
                connectWebSocket();
            };

            // WebSocket 连接
            function connectWebSocket() {
                const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
                websocket = new WebSocket(`${protocol}//${location.host}/ws`);
                
                websocket.onopen = () => {
                    updateStatus('已连接', true);
                };
                
                websocket.onmessage = async (event) => {
                    try {
                        const message = JSON.parse(event.data);
                        await handleMessage(message);
                    } catch (error) {
                        console.error('处理消息错误:', error);
                    }
                };
                
                websocket.onclose = () => {
                    updateStatus('连接断开', false);
                    setTimeout(connectWebSocket, 3000);
                };
                
                websocket.onerror = (error) => {
                    console.error('WebSocket 错误:', error);
                };
            }

            // 处理消息
            async function handleMessage(message) {
                const { type, data, from } = message;
                
                // 忽略自己发送的消息
                if (from === myClientId) return;
                
                switch (type) {
                    case 'client-id':
                        myClientId = data;
                        break;
                    case 'start-sharing':
                        if (!isSharing) {
                            setTimeout(() => {
                                if (!isSharing) {
                                    requestWatching(from);
                                }
                            }, 500);
                        }
                        break;
                    case 'request-watching':
                        if (isSharing) {
                            await sendOfferTo(from);
                        }
                        break;
                    case 'offer':
                        await handleOffer(data, from);
                        break;
                    case 'answer':
                        await handleAnswer(data, from);
                        break;
                    case 'ice-candidate':
                        await handleIceCandidate(data, from);
                        break;
                    case 'user-count':
                        document.getElementById('userCount').textContent = data;
                        break;
                    case 'stop-sharing':
                        handleStopSharing(from);
                        break;
                }
            }

            // 切换分享状态
            async function toggleShare() {
                if (isSharing) {
                    stopSharing();
                } else {
                    await startSharing();
                }
            }

            // 开始分享
            async function startSharing() {
                try {
                    // 获取屏幕流
                    localStream = await navigator.mediaDevices.getDisplayMedia({
                        video: {
                            mediaSource: 'screen',
                            width: { ideal: 1920 },
                            height: { ideal: 1080 },
                            frameRate: { ideal: 30 }
                        },
                        audio: true
                    });
                    
                    // 显示本地视频
                    const localVideo = document.getElementById('localVideo');
                    localVideo.srcObject = localStream;
                    localVideo.style.display = 'block';
                    document.getElementById('localPlaceholder').style.display = 'none';
                    
                    // 监听流结束
                    localStream.getVideoTracks()[0].onended = () => {
                        stopSharing();
                    };
                    
                    // 创建分享者连接
                    peerConnection = new RTCPeerConnection(rtcConfig);
                    
                    // 添加本地流
                    localStream.getTracks().forEach(track => {
                        peerConnection.addTrack(track, localStream);
                    });
                    
                    // ICE 候选处理
                    peerConnection.onicecandidate = (event) => {
                        if (event.candidate) {
                            sendMessage({
                                type: 'ice-candidate',
                                data: event.candidate
                            });
                        }
                    };
                    
                    // 通知开始分享
                    sendMessage({ type: 'start-sharing' });
                    
                    isSharing = true;
                    document.getElementById('shareBtn').textContent = '停止投屏';
                    document.getElementById('shareBtn').className = 'stop-btn';
                    
                } catch (error) {
                    alert('投屏失败，请确保选择了要分享的屏幕或窗口');
                }
            }

            // 停止分享
            function stopSharing() {
                if (localStream) {
                    localStream.getTracks().forEach(track => track.stop());
                    localStream = null;
                }
                
                if (peerConnection) {
                    peerConnection.close();
                    peerConnection = null;
                }
                
                // 重置UI
                document.getElementById('localVideo').style.display = 'none';
                document.getElementById('localPlaceholder').style.display = 'flex';
                document.getElementById('shareBtn').textContent = '开始投屏';
                document.getElementById('shareBtn').className = '';
                
                // 通知停止分享
                sendMessage({ type: 'stop-sharing' });
                
                isSharing = false;
            }

            // 请求观看分享
            function requestWatching(sharerId) {
                sendMessage({
                    type: 'request-watching',
                    targetId: sharerId
                });
            }

            // 发送offer给指定观看者
            async function sendOfferTo(viewerId) {
                if (!isSharing || !localStream) return;
                
                try {
                    if (peerConnection) {
                        peerConnection.close();
                    }
                    
                    peerConnection = new RTCPeerConnection(rtcConfig);
                    
                    // 添加本地流
                    localStream.getTracks().forEach(track => {
                        peerConnection.addTrack(track, localStream);
                    });
                    
                    // ICE 候选处理
                    peerConnection.onicecandidate = (event) => {
                        if (event.candidate) {
                            sendMessage({
                                type: 'ice-candidate',
                                data: event.candidate
                            });
                        }
                    };

                    // 创建并发送 offer
                    const offer = await peerConnection.createOffer({
                        offerToReceiveVideo: false,
                        offerToReceiveAudio: false
                    });
                    await peerConnection.setLocalDescription(offer);
                    
                    sendMessage({
                        type: 'offer',
                        data: offer
                    });
                } catch (error) {
                    console.error('发送offer失败:', error);
                }
            }

            // 创建观看者连接
            async function createViewerConnection() {
                if (isSharing) return;
                
                if (peerConnection) {
                    peerConnection.close();
                }
                
                peerConnection = new RTCPeerConnection(rtcConfig);
                
                // 监听远程流
                peerConnection.ontrack = (event) => {
                    if (event.streams.length > 0) {
                        const remoteVideo = document.getElementById('remoteVideo');
                        remoteVideo.srcObject = event.streams[0];
                        remoteVideo.style.display = 'block';
                        document.getElementById('remotePlaceholder').style.display = 'none';
                        
                        // 确保自动播放
                        remoteVideo.play().catch(e => {
                            console.error('自动播放失败:', e);
                            // 如果自动播放失败，尝试设置静音后播放
                            remoteVideo.muted = true;
                            remoteVideo.play().catch(err => console.error('静音播放也失败:', err));
                        });
                    }
                };
                
                // ICE 候选处理
                peerConnection.onicecandidate = (event) => {
                    if (event.candidate) {
                        sendMessage({
                            type: 'ice-candidate',
                            data: event.candidate
                        });
                    }
                };
            }

            // 处理 offer
            async function handleOffer(offer, from) {
                if (isSharing) return;
                
                await createViewerConnection();
                
                try {
                    await peerConnection.setRemoteDescription(offer);
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    
                    sendMessage({
                        type: 'answer',
                        data: answer
                    });
                } catch (error) {
                    console.error('处理offer失败:', error);
                }
            }

            // 处理 answer
            async function handleAnswer(answer, from) {
                if (!peerConnection) return;
                
                try {
                    await peerConnection.setRemoteDescription(answer);
                } catch (error) {
                    console.error('处理answer失败:', error);
                }
            }

            // 处理 ICE candidate
            async function handleIceCandidate(candidate, from) {
                if (!peerConnection) return;
                
                try {
                    await peerConnection.addIceCandidate(candidate);
                } catch (error) {
                    console.error('添加ICE候选失败:', error);
                }
            }

            // 处理停止分享
            function handleStopSharing(from) {
                if (peerConnection && !isSharing) {
                    peerConnection.close();
                    peerConnection = null;
                }
                
                // 重置远程视频
                document.getElementById('remoteVideo').style.display = 'none';
                document.getElementById('remotePlaceholder').style.display = 'flex';
                document.getElementById('remoteVideo').srcObject = null;
            }

            // 发送消息
            function sendMessage(message) {
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    websocket.send(JSON.stringify(message));
                }
            }

            // 更新状态
            function updateStatus(message, isConnected) {
                const status = document.getElementById('status');
                status.textContent = `连接状态: ${message}`;
                status.className = `status ${isConnected ? 'connected' : 'disconnected'}`;
            }

            // 页面关闭清理
            window.onbeforeunload = function() {
                if (isSharing) {
                    stopSharing();
                }
            };
        </script>
    </body>
    </html>
    """


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点处理实时通信"""
    client_id = id(websocket)
    await manager.connect(websocket)

    # 发送客户端ID和用户数量
    try:
        await websocket.send_text(json.dumps({
            "type": "client-id",
            "data": client_id
        }))

        await manager.broadcast(json.dumps({
            "type": "user-count",
            "data": len(manager.connections)
        }))
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message['from'] = client_id

            # 广播消息给其他客户端
            await manager.broadcast(json.dumps(message), websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # 更新用户数量
        await manager.broadcast(json.dumps({
            "type": "user-count",
            "data": len(manager.connections)
        }))
        # 通知停止分享
        await manager.broadcast(json.dumps({
            "type": "stop-sharing",
            "from": client_id
        }))
    except Exception:
        manager.disconnect(websocket)

if __name__ == "__main__":
    gui = ScreenShareGUI()
    gui.run()
