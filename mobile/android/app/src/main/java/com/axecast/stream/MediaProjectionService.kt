package com.axecast.stream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URI

class MediaProjectionService : Service() {

    private val CHANNEL_ID = "axecast_stream_channel"
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var webSocketClient: WebSocketClient? = null
    private var isStreaming = false
    private var serverUrl = "ws://192.168.1.108:9820"

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val resultCode = intent?.getIntExtra("RESULT_CODE", 0) ?: 0
        val dataIntent = intent?.getParcelableExtra<Intent>("DATA_INTENT")
        val roomCode = intent?.getStringExtra("ROOM_CODE") ?: ""
        serverUrl = intent?.getStringExtra("SERVER_URL") ?: "ws://192.168.1.108:9820"

        val notification = createNotification("AxeCast Live Streaming (Room $roomCode)")
        startForeground(1, notification)

        if (resultCode != 0 && dataIntent != null) {
            val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjection = projectionManager.getMediaProjection(resultCode, dataIntent)
            setupVirtualDisplay()
            connectWebSocket(roomCode, serverUrl)
        }

        return START_NOT_STICKY
    }

    private fun setupVirtualDisplay() {
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        wm.defaultDisplay.getRealMetrics(metrics)

        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        // Scale down to 720p width for ultra-smooth 60fps streaming
        val scale = if (width > 720) 720.0f / width else 1.0f
        val targetWidth = (width * scale).toInt()
        val targetHeight = (height * scale).toInt()

        imageReader = ImageReader.newInstance(targetWidth, targetHeight, PixelFormat.RGBA_8888, 2)
        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "AxeCastVirtualDisplay",
            targetWidth, targetHeight, density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader?.surface, null, null
        )

        isStreaming = true
        imageReader?.setOnImageAvailableListener({ reader ->
            if (!isStreaming) return@setOnImageAvailableListener
            val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                val planes = image.planes
                val buffer = planes[0].buffer
                val pixelStride = planes[0].pixelStride
                val rowStride = planes[0].rowStride
                val rowPadding = rowStride - pixelStride * targetWidth

                // Allocate full buffer bitmap
                val rawBitmap = Bitmap.createBitmap(targetWidth + rowPadding / pixelStride, targetHeight, Bitmap.Config.ARGB_8888)
                rawBitmap.copyPixelsFromBuffer(buffer)

                // Perfect aspect ratio: Crop out raw stride rowPadding so there is ZERO black bar or stretching!
                val cleanBitmap = if (rowPadding > 0) {
                    val cropped = Bitmap.createBitmap(rawBitmap, 0, 0, targetWidth, targetHeight)
                    rawBitmap.recycle()
                    cropped
                } else {
                    rawBitmap
                }

                val out = ByteArrayOutputStream()
                cleanBitmap.compress(Bitmap.CompressFormat.JPEG, 65, out)
                val base64Data = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)

                val frameJson = JSONObject().apply {
                    put("type", "frame")
                    put("data", base64Data)
                    put("ts", System.currentTimeMillis())
                }
                webSocketClient?.send(frameJson.toString())
                cleanBitmap.recycle()
            } catch (e: Exception) {
                // Ignore transient frame drop
            } finally {
                image.close()
            }
        }, null)
    }

    private fun connectWebSocket(roomCode: String, url: String) {
        try {
            val uri = URI(url)
            webSocketClient = object : WebSocketClient(uri) {
                override fun onOpen(handshakedata: ServerHandshake?) {
                    val createJson = JSONObject().apply {
                        put("type", "create_room")
                        put("room_code", roomCode)
                        put("device_info", JSONObject().apply {
                            put("model", Build.MODEL)
                            put("android", Build.VERSION.RELEASE)
                            put("version", "v1.0.2")
                        })
                    }
                    send(createJson.toString())
                }

                override fun onMessage(message: String?) {}
                override fun onClose(code: Int, reason: String?, remote: Boolean) {}
                override fun onError(ex: Exception?) {}
            }
            webSocketClient?.connect()
        } catch (e: Exception) {
            e.printStackTrace()
        }
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
            .setContentTitle("🪓 AxeCast Stream v1.0.2")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        isStreaming = false
        webSocketClient?.close()
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
    }
}
