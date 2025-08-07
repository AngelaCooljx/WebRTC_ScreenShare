from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import json
import logging
import signal
import sys
import os
import subprocess
import threading
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量用于控制服务器状态
shutdown_event = threading.Event()

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
                <p><strong>使用说明:</strong> 请将被投屏端与投屏端连接至相同局域网；在被投屏端上使用浏览器访问当前页面地址栏相同网址，点击下方"开始投屏"，选择"整个屏幕"窗口进行共享。</p>
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
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
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
                            frameRate: { ideal: 15 }
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
    import threading
    from fastapi import FastAPI
    import uvicorn

    # 强制退出函数
    def force_exit():
        """强制杀死当前进程"""
        try:
            # 获取当前进程ID
            pid = os.getpid()
            print(f"\n强制退出程序 (PID: {pid})...")

            # 使用taskkill强制杀死进程
            if os.name == 'nt':  # Windows
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                               capture_output=True, timeout=5)
            else:  # Unix/Linux
                os.kill(pid, signal.SIGKILL)
        except Exception as e:
            print(f"强制退出失败: {e}")
            # 最后的手段
            os._exit(1)

    # 键盘监控线程 - 独立于asyncio事件循环
    def keyboard_monitor():
        """监控键盘输入的独立线程"""
        try:
            while True:
                key = input()  # 等待用户输入
                if key.lower() in ['q', 'quit', 'exit']:
                    print("收到退出命令，立即强制退出...")
                    pid = os.getpid()
                    if os.name == 'nt':
                        subprocess.Popen(['taskkill', '/F', '/PID', str(pid)],
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    os._exit(1)
        except (EOFError, KeyboardInterrupt):
            # 处理Ctrl+C或输入结束
            print("\n检测到键盘中断，立即强制退出...")
            pid = os.getpid()
            if os.name == 'nt':
                subprocess.Popen(['taskkill', '/F', '/PID', str(pid)],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            os._exit(1)
        except Exception:
            pass

    # 信号处理函数
    def signal_handler(signum, frame):
        """处理Ctrl+C信号"""
        print(f"\n收到退出信号 ({signum})，立即强制退出...")

        # 直接强制退出，不等待
        try:
            pid = os.getpid()
            print(f"强制杀死进程 (PID: {pid})...")
            if os.name == 'nt':  # Windows
                subprocess.Popen(['taskkill', '/F', '/PID', str(pid)],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:  # Unix/Linux
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        finally:
            # 最后的手段
            os._exit(1)

    # 注册信号处理
    if os.name == 'nt':  # Windows
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    else:  # Unix/Linux
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # 创建HTTP重定向应用
    http_app = FastAPI()

    @http_app.get("/{path:path}")
    async def redirect_all(request: Request):
        host = request.headers.get("host", "localhost").split(":")[0]
        return RedirectResponse(url=f"https://{host}:443{request.url.path}", status_code=301)

    # 启动HTTP重定向服务器
    def run_http_server():
        try:
            uvicorn.run(
                http_app,
                host="0.0.0.0",
                port=80,
                log_level="warning",
                log_config=None,
                access_log=False
            )
        except Exception as e:
            if not shutdown_event.is_set():
                print(f"HTTP服务器错误: {e}")

    print(f"投屏服务启动成功！")
    print("=" * 30)
    print("按 Ctrl+C 立即强制退出程序")
    print("或者输入 'q' 然后按回车退出")
    print("=" * 30)

    # 启动键盘监控线程
    keyboard_thread = threading.Thread(target=keyboard_monitor, daemon=True)
    keyboard_thread.start()

    # 在后台线程启动HTTP重定向服务器
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    try:
        # 启动HTTPS服务器
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=443,
            log_level="warning",
            ssl_keyfile="key.pem",
            ssl_certfile="cert.pem",
            log_config=None,
            access_log=False
        )
    except KeyboardInterrupt:
        print("\n收到键盘中断，立即强制退出...")
        # 直接强制退出
        pid = os.getpid()
        if os.name == 'nt':
            subprocess.Popen(['taskkill', '/F', '/PID', str(pid)],
                             creationflags=subprocess.CREATE_NO_WINDOW)
        os._exit(1)
    except Exception as e:
        print(f"服务器启动失败: {e}")
        force_exit()
