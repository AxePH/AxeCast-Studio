package com.axecast.stream

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.media.projection.MediaProjectionManager
import android.net.wifi.WifiManager
import android.os.Bundle
import android.text.format.Formatter
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.net.Inet4Address
import java.net.NetworkInterface
import kotlin.random.Random

class MainActivity : AppCompatActivity() {

    private val REQUEST_MEDIA_PROJECTION = 1001
    private lateinit var projectionManager: MediaProjectionManager
    private lateinit var prefs: SharedPreferences
    private var isStreaming = false
    private var activeMode = "WIFI" // "WIFI" or "REMOTE"
    private var roomCode = ""
    private var pin = ""

    private lateinit var btnTabWifi: Button
    private lateinit var btnTabRemote: Button
    private lateinit var panelWifi: LinearLayout
    private lateinit var panelRemote: LinearLayout
    private lateinit var tvWifiUrl: TextView
    private lateinit var tvWifiStatus: TextView
    private lateinit var tvRoomCode: TextView
    private lateinit var tvPin: TextView
    private lateinit var tvRemoteStatus: TextView
    private lateinit var btnToggle: Button
    private lateinit var etServerUrl: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        prefs = getSharedPreferences("axecast_prefs", Context.MODE_PRIVATE)

        btnTabWifi = findViewById(R.id.btnTabWifi)
        btnTabRemote = findViewById(R.id.btnTabRemote)
        panelWifi = findViewById(R.id.panelWifi)
        panelRemote = findViewById(R.id.panelRemote)
        tvWifiUrl = findViewById(R.id.tvWifiUrl)
        tvWifiStatus = findViewById(R.id.tvWifiStatus)
        tvRoomCode = findViewById(R.id.tvRoomCode)
        tvPin = findViewById(R.id.tvPin)
        tvRemoteStatus = findViewById(R.id.tvRemoteStatus)
        btnToggle = findViewById(R.id.btnToggle)
        etServerUrl = findViewById(R.id.etServerUrl)

        val savedUrl = prefs.getString("SERVER_URL", "ws://192.168.1.108:9820")
        etServerUrl.setText(savedUrl)

        val ip = getLocalIpAddress()
        tvWifiUrl.text = "http://$ip:8080/stream"

        btnTabWifi.setOnClickListener {
            if (!isStreaming) switchMode("WIFI")
        }

        btnTabRemote.setOnClickListener {
            if (!isStreaming) switchMode("REMOTE")
        }

        btnToggle.setOnClickListener {
            if (!isStreaming) {
                if (activeMode == "REMOTE") {
                    val url = etServerUrl.text.toString().trim()
                    if (url.isEmpty()) {
                        Toast.makeText(this, "Please enter Relay Server URL", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    prefs.edit().putString("SERVER_URL", url).apply()
                }
                startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION)
            } else {
                stopStreamService()
            }
        }
    }

    private fun switchMode(mode: String) {
        activeMode = mode
        if (mode == "WIFI") {
            btnTabWifi.setBackgroundColor(0xFF0284C7.toInt())
            btnTabWifi.setTextColor(0xFFFFFFFF.toInt())
            btnTabRemote.setBackgroundColor(0xFF334155.toInt())
            btnTabRemote.setTextColor(0xFF94A3B8.toInt())
            panelWifi.visibility = View.VISIBLE
            panelRemote.visibility = View.GONE
            btnToggle.text = "📶 Start Wi-Fi Stream"
        } else {
            btnTabRemote.setBackgroundColor(0xFF7C3AED.toInt())
            btnTabRemote.setTextColor(0xFFFFFFFF.toInt())
            btnTabWifi.setBackgroundColor(0xFF334155.toInt())
            btnTabWifi.setTextColor(0xFF94A3B8.toInt())
            panelWifi.visibility = View.GONE
            panelRemote.visibility = View.VISIBLE
            btnToggle.text = "🔴 Start Remote Broadcast"
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_MEDIA_PROJECTION && resultCode == Activity.RESULT_OK && data != null) {
            val serverUrl = etServerUrl.text.toString().trim()
            isStreaming = true
            btnToggle.text = "⏹ Stop Streaming"
            btnToggle.setBackgroundColor(0xFFDC2626.toInt())
            btnTabWifi.isEnabled = false
            btnTabRemote.isEnabled = false

            if (activeMode == "WIFI") {
                tvWifiStatus.text = "🟢 Streaming on Local Wi-Fi"
            } else {
                val c1 = Random.nextInt(100, 999)
                val c2 = Random.nextInt(100, 999)
                roomCode = "$c1-$c2"
                pin = Random.nextInt(1000, 9999).toString()
                tvRoomCode.text = roomCode
                tvPin.text = "PIN: $pin"
                tvRemoteStatus.text = "🟢 Live Remote Room"
            }

            val serviceIntent = Intent(this, MediaProjectionService::class.java).apply {
                putExtra("RESULT_CODE", resultCode)
                putExtra("DATA_INTENT", data)
                putExtra("MODE", activeMode)
                putExtra("ROOM_CODE", roomCode)
                putExtra("PIN", pin)
                putExtra("SERVER_URL", serverUrl)
            }
            startForegroundService(serviceIntent)
        } else {
            Toast.makeText(this, "Screen capture permission required", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopStreamService() {
        stopService(Intent(this, MediaProjectionService::class.java))
        isStreaming = false
        btnTabWifi.isEnabled = true
        btnTabRemote.isEnabled = true
        btnToggle.setBackgroundColor(0xFF16A34A.toInt())

        if (activeMode == "WIFI") {
            tvWifiStatus.text = "⚫ Idle (Ready to stream in same Wi-Fi)"
            btnToggle.text = "📶 Start Wi-Fi Stream"
        } else {
            tvRemoteStatus.text = "⚫ Idle"
            btnToggle.text = "🔴 Start Remote Broadcast"
            tvRoomCode.text = "--- ---"
            tvPin.text = "PIN: ----"
        }
    }

    private fun getLocalIpAddress(): String {
        try {
            val en = NetworkInterface.getNetworkInterfaces()
            while (en.hasMoreElements()) {
                val intf = en.nextElement()
                val enumIpAddr = intf.inetAddresses
                while (enumIpAddr.hasMoreElements()) {
                    val inetAddress = enumIpAddr.nextElement()
                    if (!inetAddress.isLoopbackAddress && inetAddress is Inet4Address) {
                        return inetAddress.hostAddress ?: "192.168.1.xxx"
                    }
                }
            }
        } catch (ex: Exception) {
            // Fallback
        }
        return "192.168.1.xxx"
    }
}
