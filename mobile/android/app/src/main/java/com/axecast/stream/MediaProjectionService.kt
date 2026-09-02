package com.axecast.stream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.PixelFormat
import android.graphics.Rect
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.util.Base64
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import java.net.URI
import java.nio.ByteBuffer
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import org.webrtc.*

class MediaProjectionService : Service() {

    private val CHANNEL_ID = "axecast_stream_channel"
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var webSocketClient: WebSocketClient? = null
    private var httpServerSocket: ServerSocket? = null
    private val httpClients = CopyOnWriteArrayList<Socket>()
    private var backgroundThread: HandlerThread? = null
    private var backgroundHandler: Handler? = null
    private var logcatProcess: java.lang.Process? = null
    private var logcatThread: Thread? = null
    private var isStreaming = false
    private var mode = "WIFI"
    private var serverUrl = BuildConfig.SERVER_URL
    private var currentRoomCode = ""
    private var currentActivePkg = ""

    private var cachedRawBitmap: Bitmap? = null
    private var cachedCleanBitmap: Bitmap? = null
    private val isEncodingFrame = AtomicBoolean(false)
    private val frameBaos = ByteArrayOutputStream(32768)

    // WebRTC Variables
    private var peerConnectionFactory: PeerConnectionFactory? = null
    private var peerConnection: PeerConnection? = null
    private var videoSource: VideoSource? = null
    private var videoTrack: VideoTrack? = null
    private var screenCapturer: VideoCapturer? = null
    private var eglBase: EglBase? = null
    private var dataChannel: DataChannel? = null
    private var isWebRtcInitialized = false
    private var isP2pConnected = false
    private var localDataIntent: Intent? = null
    private var localResultCode: Int = 0

    override fun onBind(intent: Intent?): IBinder? = null

    private var isPinEnabled = true
    private var targetResolutionWidth = 480
    private var targetJpegQuality = 48
    private var targetFpsPacingMs = 22L
    private var screenWidth = 1080
    private var screenHeight = 2400
    private var screenDensity = 420

    private val qualityReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val newRes = intent?.getIntExtra("RESOLUTION", 480) ?: 480
            setStreamQuality(newRes)
        }
    }

    private fun setStreamQuality(res: Int) {
        targetResolutionWidth = res
        when (res) {
            360 -> {
                targetJpegQuality = 42
                targetFpsPacingMs = 18L
            }
            480 -> {
                targetJpegQuality = 48
                targetFpsPacingMs = 22L
            }
            720 -> {
                targetJpegQuality = 58
                targetFpsPacingMs = 28L
            }
            1080 -> {
                targetJpegQuality = 70
                targetFpsPacingMs = 33L
            }
            else -> {
                targetJpegQuality = 48
                targetFpsPacingMs = 22L
            }
        }
        
        // Dynamically update WebRTC VideoSource output format if it's already running
        if (screenWidth > 0 && screenHeight > 0) {
            val targetHeight = res * screenHeight / screenWidth
            videoSource?.adaptOutputFormat(res, targetHeight, 30)
            try {
                screenCapturer?.changeCaptureFormat(res, targetHeight, 30)
            } catch (e: Exception) {
                Log.e("AxeCast", "Failed to change capture format: \${e.message}")
            }
            Log.i("AxeCast", "Adjusted WebRTC resolution to \${res}x\${targetHeight}")
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        val filter = IntentFilter("com.axecast.stream.SET_QUALITY")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(qualityReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(qualityReceiver, filter)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val resultCode = intent?.getIntExtra("RESULT_CODE", 0) ?: 0
        localResultCode = resultCode
        localDataIntent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent?.getParcelableExtra("DATA_INTENT", Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent?.getParcelableExtra("DATA_INTENT")
        }
        val dataIntent = localDataIntent

        mode = intent?.getStringExtra("MODE") ?: "WIFI"
        currentRoomCode = intent?.getStringExtra("ROOM_CODE") ?: ""
        val rawUrl = intent?.getStringExtra("SERVER_URL")
        serverUrl = if (!rawUrl.isNullOrBlank()) rawUrl else BuildConfig.SERVER_URL
        isPinEnabled = intent?.getBooleanExtra("PIN_ENABLED", true) ?: true
        val initialRes = intent?.getIntExtra("RESOLUTION", 480) ?: 480
        setStreamQuality(initialRes)

        val title = if (mode == "WIFI") "AxeCast Local Wi-Fi Stream" else "AxeCast Remote Room ($currentRoomCode)"
        val notification = createNotification(title)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(1, notification)
        }

        if (resultCode != 0 && dataIntent != null) {
            isStreaming = true
            setupWindowMetrics()

            val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjection = projectionManager.getMediaProjection(resultCode, dataIntent)
            setupVirtualDisplay()

            if (mode == "WIFI") {
                startHttpMjpegServer()
            } else {
                connectWebSocket(currentRoomCode, serverUrl)
            }
            startLogcatStreaming()
            startActiveAppPoller()
        }

        return START_NOT_STICKY
    }

    private var activeAppPollerThread: Thread? = null

    private fun startActiveAppPoller() {
        activeAppPollerThread?.interrupt()
        activeAppPollerThread = Thread {
            val usm = getSystemService(Context.USAGE_STATS_SERVICE) as? android.app.usage.UsageStatsManager
            while (isStreaming && !Thread.currentThread().isInterrupted) {
                try {
                    if (usm != null) {
                        val endTime = System.currentTimeMillis()
                        val beginTime = endTime - 5000
                        val events = usm.queryEvents(beginTime, endTime)
                        val event = android.app.usage.UsageEvents.Event()
                        var topApp: String? = null
                        while (events.hasNextEvent()) {
                            events.getNextEvent(event)
                            if (event.eventType == android.app.usage.UsageEvents.Event.ACTIVITY_RESUMED) {
                                topApp = event.packageName
                            }
                        }
                        
                        if (topApp != null && topApp != currentActivePkg && 
                            !topApp.startsWith("com.android.systemui") && 
                            !topApp.startsWith("com.axecast.stream")) {
                            currentActivePkg = topApp
                            val actMsg = JSONObject().apply {
                                put("type", "active_app")
                                put("package", topApp)
                            }
                            if (dataChannel?.state() == org.webrtc.DataChannel.State.OPEN) {
                                val buffer = org.webrtc.DataChannel.Buffer(java.nio.ByteBuffer.wrap(actMsg.toString().toByteArray()), false)
                                dataChannel?.send(buffer)
                            } else {
                                webSocketClient?.send(actMsg.toString())
                            }
                            Log.i("AxeCast", "⚡ Detected foreground active app via UsageStats: $topApp")
                        }
                    }
                    Thread.sleep(1000)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {
                    try { Thread.sleep(2000) } catch (ignored: Exception) {}
                }
            }
        }.apply {
            isDaemon = true
            start()
        }
    }

    private fun setupWindowMetrics() {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val (width, height, density) = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = wm.currentWindowMetrics.bounds
            val densityDpi = resources.configuration.densityDpi
            Triple(bounds.width(), bounds.height(), densityDpi)
        } else {
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealMetrics(metrics)
            Triple(metrics.widthPixels, metrics.heightPixels, metrics.densityDpi)
        }
        screenWidth = width
        screenHeight = height
        screenDensity = density
    }

    private val pidToPkgCache = HashMap<Int, String>()

    private fun refreshRunningProcessMap() {
        try {
            val am = getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager
            am?.runningAppProcesses?.forEach { proc ->
                if (proc.pid > 0 && proc.processName.isNotEmpty()) {
                    pidToPkgCache[proc.pid] = proc.processName
                }
            }
        } catch (ignored: Exception) {}
    }

    private fun getPackageForPid(pid: Int): String {
        if (pid <= 0) return currentActivePkg
        pidToPkgCache[pid]?.let { return it }
        
        try {
            val cmdFile = java.io.File("/proc/$pid/cmdline")
            if (cmdFile.exists() && cmdFile.canRead()) {
                val raw = cmdFile.readText().trim('\u0000', ' ', '\n', '\r')
                if (raw.isNotEmpty() && !raw.startsWith("[")) {
                    val clean = raw.split("\u0000")[0].trim()
                    if (clean.isNotEmpty()) {
                        pidToPkgCache[pid] = clean
                        return clean
                    }
                }
            }
        } catch (ignored: Exception) {}

        return currentActivePkg
    }

    private fun sendInstalledPackages() {
        try {
            refreshRunningProcessMap()
            val pm = packageManager
            val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            val pkgs = JSONArray()
            for (app in apps) {
                val pkgName = app.packageName
                if (!pkgName.startsWith("com.android.internal") && !pkgName.startsWith("android") && !pkgName.startsWith("com.google.android.overlay")) {
                    pkgs.put(pkgName)
                }
            }
            val pkgMsg = JSONObject().apply {
                put("type", "packages_list")
                put("packages", pkgs)
            }
            
            if (dataChannel?.state() == DataChannel.State.OPEN) {
                val buffer = DataChannel.Buffer(ByteBuffer.wrap(pkgMsg.toString().toByteArray()), false)
                dataChannel?.send(buffer)
            } else {
                webSocketClient?.send(pkgMsg.toString())
            }
        } catch (e: Exception) {
            Log.e("AxeCast", "Error sending packages: ${e.message}")
        }
    }

    private fun startLogcatStreaming() {
        logcatThread?.interrupt()
        logcatThread = Thread {
            val threadtimeRegex = Regex("""^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:(]+):\s*(.*)$""")
            val appSwitchRegex = Regex("""(?:cmp=|Displayed\s+|ActivityRecord\{[^\s]+\s+u\d+\s+|Window\{[^\s]+\s+u\d+\s+|Focus moved to Window\{[^\s]+\s+|ResumedActivity: ActivityRecord\{[^\s]+\s+u\d+\s+)([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)""")
            val procStartRegex = Regex("""(?:Start proc\s+(\d+):([a-zA-Z0-9_.]+)|pid=(\d+)\s+package=([a-zA-Z0-9_.]+))""")

            while (isStreaming && !Thread.currentThread().isInterrupted) {
                try {
                    refreshRunningProcessMap()
                    try { Runtime.getRuntime().exec("logcat -c").waitFor() } catch (ignored: Exception) {}
                    val process = Runtime.getRuntime().exec(arrayOf("logcat", "-v", "threadtime"))
                    logcatProcess = process
                    val reader = BufferedReader(InputStreamReader(process.inputStream))

                    while (isStreaming && !Thread.currentThread().isInterrupted) {
                        val line = reader.readLine() ?: break
                        if (webSocketClient?.isOpen == true || dataChannel?.state() == DataChannel.State.OPEN) {
                            if (line.contains("proc") || line.contains("pid=")) {
                                val pMatch = procStartRegex.find(line)
                                if (pMatch != null) {
                                    val pidFound = (pMatch.groupValues[1].ifEmpty { pMatch.groupValues[3] }).toIntOrNull() ?: 0
                                    val pkgFound = pMatch.groupValues[2].ifEmpty { pMatch.groupValues[4] }
                                    if (pidFound > 0 && pkgFound.isNotEmpty()) {
                                        pidToPkgCache[pidFound] = pkgFound
                                    }
                                }
                            }

                            if (line.contains("Activity") || line.contains("Window") || line.contains("Displayed") || line.contains("cmp=")) {
                                val swMatch = appSwitchRegex.find(line)
                                if (swMatch != null) {
                                    val swPkg = swMatch.groupValues[1]
                                    if (!swPkg.startsWith("com.android.systemui") && !swPkg.startsWith("com.axecast.stream") && swPkg != currentActivePkg) {
                                        currentActivePkg = swPkg
                                        val actMsg = JSONObject().apply {
                                            put("type", "active_app")
                                            put("package", swPkg)
                                        }
                                        if (dataChannel?.state() == DataChannel.State.OPEN) {
                                            val buffer = DataChannel.Buffer(ByteBuffer.wrap(actMsg.toString().toByteArray(Charsets.UTF_8)), false)
                                            dataChannel?.send(buffer)
                                        } else {
                                            webSocketClient?.send(actMsg.toString())
                                        }
                                    }
                                }
                            }

                            val match = threadtimeRegex.find(line)
                            val logJson = JSONObject().apply {
                                put("type", "log")
                                put("raw", line)
                                if (match != null) {
                                    val (time, pidStr, tidStr, level, tag, msg) = match.destructured
                                    val pid = pidStr.trim().toIntOrNull() ?: 0
                                    var pkg = getPackageForPid(pid)
                                    if (pkg.isEmpty()) {
                                        pkg = if (tag.contains(".")) tag.trim() else currentActivePkg
                                    }
                                    put("timestamp", time)
                                    put("pid", pid)
                                    put("level", level)
                                    put("tag", tag.trim())
                                    put("message", msg)
                                    put("package", pkg)
                                } else {
                                    put("timestamp", "")
                                    put("level", "I")
                                    put("tag", "")
                                    put("message", line)
                                    put("package", currentActivePkg)
                                }
                            }

                            val rawJson = logJson.toString()
                            if (dataChannel?.state() == DataChannel.State.OPEN) {
                                val buffer = DataChannel.Buffer(ByteBuffer.wrap(rawJson.toByteArray(Charsets.UTF_8)), false)
                                dataChannel?.send(buffer)
                            } else if (webSocketClient?.isOpen == true) {
                                webSocketClient?.send(rawJson)
                            }
                        }
                    }
                    try { Thread.sleep(1000) } catch (ignored: Exception) {}
                } catch (e: Exception) {
                    try { Thread.sleep(1500) } catch (ignored: Exception) {}
                }
            }
        }.apply {
            priority = Thread.NORM_PRIORITY
            start()
        }
    }

    private fun handleRemoteButton(action: String) {
        try {
            when (action.lowercase()) {
                "home" -> {
                    val homeIntent = Intent(Intent.ACTION_MAIN).apply {
                        addCategory(Intent.CATEGORY_HOME)
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    startActivity(homeIntent)
                }
            }
        } catch (e: Exception) {
            Log.e("AxeCast", "Failed to handle remote button $action: ${e.message}")
        }
    }

    private fun initializeWebRTC() {
        if (isWebRtcInitialized) return
        
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(this)
                .setEnableInternalTracer(true)
                .createInitializationOptions()
        )
        eglBase = EglBase.create()
        val options = PeerConnectionFactory.Options()
        
        val defaultVideoEncoderFactory = DefaultVideoEncoderFactory(
            eglBase?.eglBaseContext, true, true
        )
        val defaultVideoDecoderFactory = DefaultVideoDecoderFactory(eglBase?.eglBaseContext)
        
        peerConnectionFactory = PeerConnectionFactory.builder()
            .setOptions(options)
            .setVideoEncoderFactory(defaultVideoEncoderFactory)
            .setVideoDecoderFactory(defaultVideoDecoderFactory)
            .createPeerConnectionFactory()
            
        val capturer = localDataIntent?.let {
            ScreenCapturerAndroid(it, object : MediaProjection.Callback() {
                override fun onStop() {
                    super.onStop()
                    Log.w("AxeCast", "ScreenCapturer onStop")
                }
            })
        }
        screenCapturer = capturer
        
        if (capturer != null) {
            val surfaceTextureHelper = SurfaceTextureHelper.create("CaptureThread", eglBase?.eglBaseContext)
            videoSource = peerConnectionFactory?.createVideoSource(capturer.isScreencast)
            capturer.initialize(surfaceTextureHelper, this, videoSource!!.capturerObserver)
            
            val targetHeight = ((targetResolutionWidth * screenHeight / screenWidth) / 2) * 2
            val targetWidth = (targetResolutionWidth / 2) * 2
            capturer.startCapture(targetWidth, targetHeight, 30)
            
            videoTrack = peerConnectionFactory?.createVideoTrack("video_track", videoSource)
        }
        
        isWebRtcInitialized = true
        Log.i("AxeCast", "✅ WebRTC Initialized & ScreenCapturer started")
    }

    private fun createAndSendOffer() {
        initializeWebRTC()
        
        if (peerConnection == null) {
            val iceServers = listOf(
                PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
                PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer(),
                PeerConnection.IceServer.builder("stun:stun2.l.google.com:19302").createIceServer(),
                PeerConnection.IceServer.builder("turn:openrelay.metered.ca:80")
                    .setUsername("openrelay")
                    .setPassword("openrelay")
                    .createIceServer(),
                PeerConnection.IceServer.builder("turn:openrelay.metered.ca:443")
                    .setUsername("openrelay")
                    .setPassword("openrelay")
                    .createIceServer(),
                PeerConnection.IceServer.builder("turn:openrelay.metered.ca:443?transport=tcp")
                    .setUsername("openrelay")
                    .setPassword("openrelay")
                    .createIceServer()
            )
            val rtcConfig = PeerConnection.RTCConfiguration(iceServers)
            rtcConfig.sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            
            peerConnection = peerConnectionFactory?.createPeerConnection(rtcConfig, object : PeerConnection.Observer {
                override fun onSignalingChange(state: PeerConnection.SignalingState?) {
                    Log.d("AxeCast", "WebRTC Signaling: $state")
                }
                override fun onIceConnectionChange(state: PeerConnection.IceConnectionState?) {
                    Log.i("AxeCast", "⚡ WebRTC ICE State: $state")
                    if (state == PeerConnection.IceConnectionState.CONNECTED) {
                        isP2pConnected = true
                        sendStatus("CONNECTED", "⚡ WebRTC P2P Connected (Room $currentRoomCode)", currentRoomCode, "")
                    } else if (state == PeerConnection.IceConnectionState.DISCONNECTED || state == PeerConnection.IceConnectionState.FAILED) {
                        isP2pConnected = false
                        sendStatus("CONNECTED", "🔵 Cloud Relay Stream (Room $currentRoomCode)", currentRoomCode, "")
                    }
                }
                override fun onIceConnectionReceivingChange(receiving: Boolean) {}
                override fun onIceGatheringChange(state: PeerConnection.IceGatheringState?) {}
                override fun onIceCandidate(candidate: IceCandidate?) {
                    if (candidate != null && webSocketClient?.isOpen == true) {
                        val json = JSONObject().apply {
                            put("type", "webrtc_ice")
                            put("room_code", currentRoomCode)
                            put("candidate", JSONObject().apply {
                                put("sdpMid", candidate.sdpMid)
                                put("sdpMLineIndex", candidate.sdpMLineIndex)
                                put("candidate", candidate.sdp)
                            })
                        }
                        webSocketClient?.send(json.toString())
                    }
                }
                override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>?) {}
                override fun onAddStream(stream: MediaStream?) {}
                override fun onRemoveStream(stream: MediaStream?) {}
                override fun onDataChannel(dc: DataChannel?) {
                    Log.i("AxeCast", "⚡ Received remote DataChannel: ${dc?.label()}")
                    dc?.registerObserver(object : DataChannel.Observer {
                        override fun onBufferedAmountChange(p0: Long) {}
                        override fun onStateChange() {
                            Log.i("AxeCast", "⚡ Remote DataChannel State: ${dc.state()}")
                        }
                        override fun onMessage(buffer: DataChannel.Buffer?) {
                            if (buffer != null) {
                                val bytes = ByteArray(buffer.data.remaining())
                                buffer.data.get(bytes)
                                val text = String(bytes, Charsets.UTF_8)
                                handleIncomingControlMessage(text)
                            }
                        }
                    })
                }
                override fun onRenegotiationNeeded() {}
                override fun onAddTrack(receiver: RtpReceiver?, mediaStreams: Array<out MediaStream>?) {}
            })
            
            val dcInit = DataChannel.Init()
            dcInit.ordered = true
            dataChannel = peerConnection?.createDataChannel("data", dcInit)
            dataChannel?.registerObserver(object : DataChannel.Observer {
                override fun onBufferedAmountChange(p0: Long) {}
                override fun onStateChange() {
                    Log.i("AxeCast", "⚡ WebRTC DataChannel State: ${dataChannel?.state()}")
                }
                override fun onMessage(buffer: DataChannel.Buffer?) {
                    if (buffer != null) {
                        val bytes = ByteArray(buffer.data.remaining())
                        buffer.data.get(bytes)
                        val text = String(bytes, Charsets.UTF_8)
                        handleIncomingControlMessage(text)
                    }
                }
            })
            
            if (videoTrack != null) {
                peerConnection?.addTrack(videoTrack)
            }
        }
        
        val sdpMediaConstraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "false"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "false"))
        }
        
        peerConnection?.createOffer(object : SdpObserver {
            override fun onCreateSuccess(desc: SessionDescription?) {
                peerConnection?.setLocalDescription(this, desc)
                if (desc != null && webSocketClient?.isOpen == true) {
                    val json = JSONObject().apply {
                        put("type", "webrtc_offer")
                        put("room_code", currentRoomCode)
                        put("sdp", desc.description)
                    }
                    webSocketClient?.send(json.toString())
                    Log.i("AxeCast", "📤 WebRTC Offer sent for Room $currentRoomCode")
                }
            }
            override fun onSetSuccess() {
                Log.d("AxeCast", "Local description set successfully")
            }
            override fun onCreateFailure(p0: String?) {
                Log.e("AxeCast", "Failed to create WebRTC Offer: $p0")
            }
            override fun onSetFailure(p0: String?) {
                Log.e("AxeCast", "Failed to set local description: $p0")
            }
        }, sdpMediaConstraints)
    }

    private fun handleWebRtcAnswer(sdp: String) {
        val answer = SessionDescription(SessionDescription.Type.ANSWER, sdp)
        peerConnection?.setRemoteDescription(object : SdpObserver {
            override fun onCreateSuccess(p0: SessionDescription?) {}
            override fun onSetSuccess() {
                Log.i("AxeCast", "✅ Remote description (Answer) set successfully")
            }
            override fun onCreateFailure(p0: String?) {}
            override fun onSetFailure(p0: String?) {
                Log.e("AxeCast", "Failed to set remote description: $p0")
            }
        }, answer)
    }

    private fun handleWebRtcIce(candidateData: JSONObject) {
        try {
            val sdpMid = candidateData.optString("sdpMid")
            val sdpMLineIndex = candidateData.optInt("sdpMLineIndex")
            val sdp = candidateData.optString("candidate")
            val iceCandidate = IceCandidate(sdpMid, sdpMLineIndex, sdp)
            peerConnection?.addIceCandidate(iceCandidate)
            Log.d("AxeCast", "🧊 Added ICE Candidate from remote")
        } catch (e: Exception) {
            Log.e("AxeCast", "Error adding ICE candidate: ${e.message}")
        }
    }

    private fun startHttpMjpegServer() {
        Thread {
            try {
                httpServerSocket = ServerSocket(8080)
                Log.i("AxeCast", "Local Wi-Fi MJPEG server started on port 8080")
                sendStatus("CONNECTED", "🟢 Streaming over Local Wi-Fi")

                while (isStreaming) {
                    val client = httpServerSocket?.accept() ?: break
                    httpClients.add(client)
                    Thread { handleHttpClient(client) }.start()
                }
            } catch (e: Exception) {
            }
        }.start()
    }

    private fun handleHttpClient(socket: Socket) {
        try {
            val out = socket.getOutputStream()
            val responseHeader = ("HTTP/1.1 200 OK\r\n" +
                    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n" +
                    "Cache-Control: no-cache, no-store, must-revalidate\r\n" +
                    "Pragma: no-cache\r\n" +
                    "Expires: 0\r\n" +
                    "Access-Control-Allow-Origin: *\r\n\r\n").toByteArray()
            out.write(responseHeader)
            out.flush()

            while (isStreaming && !socket.isClosed) {
                Thread.sleep(100)
            }
        } catch (e: Exception) {
        } finally {
            httpClients.remove(socket)
            try { socket.close() } catch (ignored: Exception) {}
        }
    }

    private fun setupVirtualDisplay() {
        val scale = if (screenWidth > targetResolutionWidth) targetResolutionWidth.toFloat() / screenWidth else 1.0f
        val targetWidth = (screenWidth * scale).toInt()
        val targetHeight = (screenHeight * scale).toInt()

        backgroundThread = HandlerThread("AxeCastFrameEncoder", android.os.Process.THREAD_PRIORITY_DISPLAY).apply { start() }
        backgroundHandler = Handler(backgroundThread!!.looper)

        var lastFrameTimestamp = 0L

        imageReader = ImageReader.newInstance(targetWidth, targetHeight, PixelFormat.RGBA_8888, 2)
        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "AxeCastVirtualDisplay",
            targetWidth, targetHeight, screenDensity,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader?.surface, null, backgroundHandler
        )

        imageReader?.setOnImageAvailableListener({ reader ->
            if (!isStreaming) return@setOnImageAvailableListener
            val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener

            val now = System.currentTimeMillis()
            if (now - lastFrameTimestamp < targetFpsPacingMs) {
                image.close()
                return@setOnImageAvailableListener
            }

            if (!isEncodingFrame.compareAndSet(false, true)) {
                image.close()
                return@setOnImageAvailableListener
            }
            lastFrameTimestamp = now

            try {
                val planes = image.planes
                val buffer = planes[0].buffer
                val pixelStride = planes[0].pixelStride
                val rowStride = planes[0].rowStride
                val rowPadding = rowStride - pixelStride * targetWidth
                val rawWidth = targetWidth + rowPadding / pixelStride

                if (cachedRawBitmap == null || cachedRawBitmap?.width != rawWidth || cachedRawBitmap?.height != targetHeight) {
                    cachedRawBitmap?.recycle()
                    cachedRawBitmap = Bitmap.createBitmap(rawWidth, targetHeight, Bitmap.Config.ARGB_8888)
                }

                val rawBitmap = cachedRawBitmap!!
                rawBitmap.copyPixelsFromBuffer(buffer)

                val cleanBitmap = if (rowPadding > 0) {
                    if (cachedCleanBitmap == null || cachedCleanBitmap?.width != targetWidth || cachedCleanBitmap?.height != targetHeight) {
                        cachedCleanBitmap?.recycle()
                        cachedCleanBitmap = Bitmap.createBitmap(targetWidth, targetHeight, Bitmap.Config.ARGB_8888)
                    }
                    val canvas = Canvas(cachedCleanBitmap!!)
                    canvas.drawBitmap(rawBitmap, Rect(0, 0, targetWidth, targetHeight), Rect(0, 0, targetWidth, targetHeight), null)
                    cachedCleanBitmap!!
                } else {
                    rawBitmap
                }

                frameBaos.reset()
                cleanBitmap.compress(Bitmap.CompressFormat.JPEG, targetJpegQuality, frameBaos)
                val jpegBytes = frameBaos.toByteArray()

                if (mode == "WIFI") {
                    val frameHeader = ("--frame\r\n" +
                            "Content-Type: image/jpeg\r\n" +
                            "Content-Length: ${jpegBytes.size}\r\n\r\n").toByteArray()
                    for (client in httpClients) {
                        try {
                            val clientOut = client.getOutputStream()
                            clientOut.write(frameHeader)
                            clientOut.write(jpegBytes)
                            clientOut.write("\r\n".toByteArray())
                            clientOut.flush()
                        } catch (e: Exception) {
                            httpClients.remove(client)
                        }
                    }
                } else if (!isP2pConnected && webSocketClient?.isOpen == true) {
                    val b64 = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
                    val frameMsg = JSONObject().apply {
                        put("type", "frame")
                        put("room_code", currentRoomCode)
                        put("data", b64)
                        put("ts", now)
                    }
                    webSocketClient?.send(frameMsg.toString())
                }
            } catch (e: Exception) {
            } finally {
                image.close()
                isEncodingFrame.set(false)
            }
        }, backgroundHandler)
    }

    private fun handleShellCommand(cmdId: String, command: String) {
        Thread {
            try {
                Log.i("AxeCast", "🖥️ Executing remote shell command: $command")
                val process = Runtime.getRuntime().exec(arrayOf("sh", "-c", command))
                
                // Read stdout
                Thread {
                    try {
                        val reader = BufferedReader(InputStreamReader(process.inputStream))
                        while (true) {
                            val line = reader.readLine() ?: break
                            sendShellOutput(cmdId, line, false)
                        }
                    } catch (ignored: Exception) {}
                }.start()
                
                // Read stderr
                Thread {
                    try {
                        val errReader = BufferedReader(InputStreamReader(process.errorStream))
                        while (true) {
                            val line = errReader.readLine() ?: break
                            sendShellOutput(cmdId, line, true)
                        }
                    } catch (ignored: Exception) {}
                }.start()
                
                val exitCode = process.waitFor()
                sendShellDone(cmdId, exitCode)
                Log.i("AxeCast", "🏁 Remote shell command done (code $exitCode): $command")
            } catch (e: Exception) {
                Log.e("AxeCast", "Error executing shell: ${e.message}")
                sendShellOutput(cmdId, "Error: ${e.message}", true)
                sendShellDone(cmdId, -1)
            }
        }.start()
    }

    private fun sendShellOutput(cmdId: String, text: String, isErr: Boolean) {
        val json = JSONObject().apply {
            put("type", "shell_output")
            put("id", cmdId)
            put("text", text)
            put("is_err", isErr)
        }
        sendControlMessage(json.toString())
    }

    private fun sendShellDone(cmdId: String, exitCode: Int) {
        val json = JSONObject().apply {
            put("type", "shell_done")
            put("id", cmdId)
            put("exit_code", exitCode)
        }
        sendControlMessage(json.toString())
    }

    private fun sendControlMessage(msg: String) {
        if (dataChannel?.state() == DataChannel.State.OPEN) {
            val buffer = DataChannel.Buffer(ByteBuffer.wrap(msg.toByteArray()), false)
            dataChannel?.send(buffer)
        } else if (webSocketClient?.isOpen == true) {
            webSocketClient?.send(msg)
        }
    }

    private val adbSockets = java.util.concurrent.ConcurrentHashMap<String, Socket>()

    private fun findAdbPort(): Int {
        val portProp = try {
            val p = Runtime.getRuntime().exec(arrayOf("getprop", "service.adb.tcp.port"))
            BufferedReader(InputStreamReader(p.inputStream)).readLine()?.trim()?.toIntOrNull()
        } catch (e: Exception) { null }
        if (portProp != null && portProp > 0) return portProp
        return 5555
    }

    private fun handleAdbOpen(cid: String) {
        Thread {
            try {
                val adbPort = findAdbPort()
                Log.i("AxeCast", "🔌 Opening ADB tunnel socket for CID $cid -> 127.0.0.1:$adbPort")
                val socket = Socket()
                socket.connect(java.net.InetSocketAddress("127.0.0.1", adbPort), 1500)
                adbSockets[cid] = socket
                val inStream = socket.getInputStream()
                val buffer = ByteArray(32768)

                val openAck = JSONObject().apply {
                    put("type", "adb_open_ack")
                    put("cid", cid)
                    put("success", true)
                }
                sendControlMessage(openAck.toString())

                while (isStreaming && !socket.isClosed) {
                    val read = inStream.read(buffer)
                    if (read == -1) break
                    val b64 = Base64.encodeToString(buffer, 0, read, Base64.NO_WRAP)
                    val dataMsg = JSONObject().apply {
                        put("type", "adb_data")
                        put("cid", cid)
                        put("data", b64)
                    }
                    sendControlMessage(dataMsg.toString())
                }
            } catch (e: Exception) {
                Log.e("AxeCast", "ADB tunnel socket error for CID $cid: ${e.message}")
                val openErr = JSONObject().apply {
                    put("type", "adb_open_ack")
                    put("cid", cid)
                    put("success", false)
                    put("error", e.message ?: "Failed to connect to local adbd")
                }
                sendControlMessage(openErr.toString())
            } finally {
                try { adbSockets.remove(cid)?.close() } catch (ignored: Exception) {}
                val closeMsg = JSONObject().apply {
                    put("type", "adb_close")
                    put("cid", cid)
                }
                sendControlMessage(closeMsg.toString())
            }
        }.start()
    }

    private fun handleAdbData(cid: String, b64Data: String) {
        try {
            val bytes = Base64.decode(b64Data, Base64.NO_WRAP)
            val socket = adbSockets[cid]
            if (socket != null && !socket.isClosed) {
                socket.getOutputStream().write(bytes)
                socket.getOutputStream().flush()
            }
        } catch (e: Exception) {
            Log.e("AxeCast", "Error writing ADB data: ${e.message}")
        }
    }

    private fun handleAdbClose(cid: String) {
        try {
            adbSockets.remove(cid)?.close()
        } catch (ignored: Exception) {}
    }

    private fun handleIncomingControlMessage(message: String) {
        try {
            val json = JSONObject(message)
            val msgType = json.optString("type")
            if (msgType == "shell_exec") {
                val cmdId = json.optString("id", System.currentTimeMillis().toString())
                val cmd = json.optString("command", "")
                if (cmd.isNotEmpty()) {
                    handleShellCommand(cmdId, cmd)
                }
            } else if (msgType == "adb_open") {
                val cid = json.optString("cid")
                if (cid.isNotEmpty()) {
                    handleAdbOpen(cid)
                }
            } else if (msgType == "adb_data") {
                val cid = json.optString("cid")
                val data = json.optString("data")
                if (cid.isNotEmpty() && data.isNotEmpty()) {
                    handleAdbData(cid, data)
                }
            } else if (msgType == "adb_close") {
                val cid = json.optString("cid")
                if (cid.isNotEmpty()) {
                    handleAdbClose(cid)
                }
            } else if (msgType == "button") {
                val action = json.optString("action")
                handleRemoteButton(action)
            } else if (msgType == "webrtc_answer") {
                val sdp = json.optString("sdp")
                if (sdp.isNotEmpty()) {
                    handleWebRtcAnswer(sdp)
                }
            } else if (msgType == "webrtc_ice") {
                val candidate = json.optJSONObject("candidate")
                if (candidate != null) {
                    handleWebRtcIce(candidate)
                }
            } else if (msgType == "request_offer") {
                Log.i("AxeCast", "👤 Viewer requested offer -> creating & sending WebRTC offer")
                Handler(Looper.getMainLooper()).post {
                    createAndSendOffer()
                }
            }
        } catch (e: Exception) {
            Log.e("AxeCast", "Error in handleIncomingControlMessage: ${e.message}")
        }
    }

    private fun connectWebSocket(roomCode: String, rawUrl: String) {
        var cleanUrl = rawUrl.trim()
        if (cleanUrl.startsWith("https://", ignoreCase = true)) {
            cleanUrl = "wss://" + cleanUrl.substring(8)
        } else if (cleanUrl.startsWith("http://", ignoreCase = true)) {
            cleanUrl = "ws://" + cleanUrl.substring(7)
        } else if (!cleanUrl.startsWith("ws://", ignoreCase = true) && !cleanUrl.startsWith("wss://", ignoreCase = true)) {
            cleanUrl = "wss://" + cleanUrl
        }

        val cloudDomains = listOf("onrender.com", "fly.dev", "railway.app", "herokuapp.com", "pages.dev", "appspot.com")
        if (cloudDomains.any { cleanUrl.contains(it, ignoreCase = true) }) {
            cleanUrl = cleanUrl.replace(":9820", "").replace(":8080", "")
        }

        try {
            val uri = URI(cleanUrl)
            sendStatus("CONNECTING", "⏳ Connecting to Server...")
            
            webSocketClient = object : WebSocketClient(uri) {
                init {
                    try {
                        setTcpNoDelay(true)
                        setReuseAddr(true)
                    } catch (ignored: Exception) {}
                }

                override fun onOpen(handshakedata: ServerHandshake?) {
                    Log.i("AxeCast", "✅ WebSocket connection OPEN")
                    val pinToSend = if (isPinEnabled) String.format("%04d", (1000..9999).random()) else ""
                    val createJson = JSONObject().apply {
                        put("type", "create_room")
                        put("room_code", "")
                        put("pin", pinToSend)
                        put("device_info", JSONObject().apply {
                            put("model", Build.MODEL)
                            put("android", Build.VERSION.RELEASE)
                            put("version", "v1.0.6")
                        })
                    }
                    send(createJson.toString())
                    sendInstalledPackages()
                }

                override fun onMessage(message: String?) {
                    if (message == null) return
                    try {
                        val json = JSONObject(message)
                        val msgType = json.optString("type")
                        if (msgType == "room_created") {
                            val serverAssigned = json.optString("room_code", "")
                            currentRoomCode = serverAssigned
                            val formattedCode = if (serverAssigned.replace("-", "").length == 6) {
                                val digits = serverAssigned.replace("-", "").trim()
                                "${digits.substring(0, 3)}-${digits.substring(3)}"
                            } else serverAssigned
                            val pin = json.optString("pin", "")
                            sendStatus("CONNECTED", "🟢 Live Streaming (Room $formattedCode)", formattedCode, pin)
                            sendInstalledPackages()
                            
                            // Initialize WebRTC and prepare initial offer
                            Handler(Looper.getMainLooper()).post {
                                createAndSendOffer()
                            }
                        } else {
                            handleIncomingControlMessage(message)
                        }
                    } catch (e: Exception) {
                        Log.e("AxeCast", "Error in onMessage: ${e.message}")
                    }
                }
                
                override fun onClose(code: Int, reason: String?, remote: Boolean) {
                    sendStatus("DISCONNECTED", "⚫ Disconnected from server")
                }
                
                override fun onError(ex: Exception?) {
                    val err = ex?.message ?: "Connection error"
                    sendStatus("ERROR", "❌ Server error: $err")
                }
            }

            if (cleanUrl.startsWith("wss://", ignoreCase = true)) {
                val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
                    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
                    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
                })
                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, trustAllCerts, SecureRandom())
                webSocketClient?.setSocketFactory(sslContext.socketFactory)
            }

            webSocketClient?.connect()
        } catch (e: Exception) {
            sendStatus("ERROR", "❌ Failed: ${e.message}")
        }
    }

    private fun sendStatus(status: String, text: String, roomCode: String = "", pin: String = "") {
        val intent = Intent("com.axecast.stream.STATUS_UPDATE").apply {
            putExtra("STATUS", status)
            putExtra("TEXT", text)
            putExtra("ROOM_CODE", roomCode)
            putExtra("PIN", pin)
            setPackage(packageName)
        }
        sendBroadcast(intent)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AxeCast Streaming Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(contentText: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🪓 AxeCast Stream v1.0.6")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        isStreaming = false
        try { activeAppPollerThread?.interrupt() } catch (ignored: Exception) {}
        try { logcatProcess?.destroy() } catch (ignored: Exception) {}
        try { logcatThread?.interrupt() } catch (ignored: Exception) {}
        try { httpServerSocket?.close() } catch (ignored: Exception) {}
        for (c in httpClients) {
            try { c.close() } catch (ignored: Exception) {}
        }
        httpClients.clear()
        
        try { dataChannel?.dispose() } catch (ignored: Exception) {}
        try { videoTrack?.dispose() } catch (ignored: Exception) {}
        try { videoSource?.dispose() } catch (ignored: Exception) {}
        try { screenCapturer?.stopCapture() } catch (ignored: Exception) {}
        try { screenCapturer?.dispose() } catch (ignored: Exception) {}
        try { peerConnection?.dispose() } catch (ignored: Exception) {}
        try { eglBase?.release() } catch (ignored: Exception) {}
        
        webSocketClient?.close()
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        try {
            backgroundThread?.quitSafely()
            backgroundThread = null
            backgroundHandler = null
        } catch (ignored: Exception) {}
        try {
            unregisterReceiver(qualityReceiver)
        } catch (ignored: Exception) {}
        sendStatus("IDLE", "⚫ Idle")
    }
}
