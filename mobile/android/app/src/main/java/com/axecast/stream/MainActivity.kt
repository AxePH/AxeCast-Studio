package com.axecast.stream

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.widget.SwitchCompat
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.Inet4Address
import java.net.NetworkInterface

class MainActivity : AppCompatActivity() {

    private val REQUEST_MEDIA_PROJECTION = 1001
    private val REQUEST_PERMISSIONS = 2001
    private lateinit var projectionManager: MediaProjectionManager
    private lateinit var prefs: SharedPreferences
    private var isStreaming = false
    private var activeMode = "WIFI"
    private var roomCode = ""
    private var pin = ""

    private lateinit var btnTabWifi: Button
    private lateinit var btnTabRemote: Button
    private lateinit var panelWifi: LinearLayout
    private lateinit var panelRemote: LinearLayout
    private lateinit var tvWifiUrl: TextView
    private lateinit var tvWifiStatus: TextView
    private lateinit var tvRoomCode: TextView
    private lateinit var switchPinLock: SwitchCompat
    private lateinit var tvPin: TextView
    private lateinit var tvRemoteStatus: TextView
    private lateinit var btnToggle: Button
    private lateinit var etServerUrl: EditText

    private lateinit var btnRes360: Button
    private lateinit var btnRes480: Button
    private lateinit var btnRes720: Button
    private lateinit var btnRes1080: Button
    private lateinit var tvActiveResHint: TextView
    private var selectedResolution = 480

    private lateinit var tvPermNotif: TextView
    private lateinit var tvPermLogs: TextView
    private lateinit var tvPermPkgs: TextView

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val status = intent?.getStringExtra("STATUS") ?: ""
            val text = intent?.getStringExtra("TEXT") ?: ""
            val assignedCode = intent?.getStringExtra("ROOM_CODE") ?: ""
            val assignedPin = intent?.getStringExtra("PIN") ?: ""

            runOnUiThread {
                if (assignedCode.isNotEmpty()) {
                    roomCode = assignedCode
                    tvRoomCode.text = roomCode
                }
                if (assignedPin.isNotEmpty()) {
                    pin = assignedPin
                    if (switchPinLock.isChecked) {
                        tvPin.text = "PIN: $pin"
                        tvPin.setTextColor(0xFF38BDF8.toInt())
                    }
                } else if (assignedCode.isNotEmpty() && !switchPinLock.isChecked) {
                    tvPin.text = "PIN: OFF (Open)"
                    tvPin.setTextColor(0xFF94A3B8.toInt())
                }

                if (activeMode == "WIFI") {
                    tvWifiStatus.text = text
                } else {
                    tvRemoteStatus.text = text
                    if (status == "ERROR") {
                        tvRemoteStatus.setTextColor(0xFFEF4444.toInt())
                        tvRoomCode.text = "--- ---"
                    } else if (status == "CONNECTED") {
                        tvRemoteStatus.setTextColor(0xFF22C55E.toInt())
                    }
                }
            }
        }
    }

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
        switchPinLock = findViewById(R.id.switchPinLock)
        tvPin = findViewById(R.id.tvPin)
        tvRemoteStatus = findViewById(R.id.tvRemoteStatus)
        btnToggle = findViewById(R.id.btnToggle)
        etServerUrl = findViewById(R.id.etServerUrl)

        setupResolutionSelector()

        tvPermNotif = findViewById(R.id.tvPermNotif)
        tvPermLogs = findViewById(R.id.tvPermLogs)
        tvPermPkgs = findViewById(R.id.tvPermPkgs)

        val isPinLock = prefs.getBoolean("PIN_LOCK_ENABLED", true)
        switchPinLock.isChecked = isPinLock
        updatePinUi(isPinLock)

        switchPinLock.setOnCheckedChangeListener { _, isChecked ->
            prefs.edit().putBoolean("PIN_LOCK_ENABLED", isChecked).apply()
            updatePinUi(isChecked)
        }

        val lastBuildUrl = prefs.getString("LAST_BUILD_URL", "") ?: ""
        val savedUrl = prefs.getString("SERVER_URL", "") ?: ""
        if (BuildConfig.SERVER_URL.isNotEmpty() && BuildConfig.SERVER_URL != lastBuildUrl) {
            etServerUrl.setText(BuildConfig.SERVER_URL)
            prefs.edit()
                .putString("SERVER_URL", BuildConfig.SERVER_URL)
                .putString("LAST_BUILD_URL", BuildConfig.SERVER_URL)
                .apply()
        } else if (savedUrl.isNotEmpty()) {
            etServerUrl.setText(savedUrl)
        } else if (BuildConfig.SERVER_URL.isNotEmpty()) {
            etServerUrl.setText(BuildConfig.SERVER_URL)
        }

        val rowPermLogs = findViewById<View>(R.id.rowPermLogs)
        rowPermLogs?.setOnClickListener {
            if (!hasUsageAccessPermission()) {
                promptUsageAccessPermission()
            } else {
                Toast.makeText(this, "Active App Detection permission is already granted! 🟢", Toast.LENGTH_SHORT).show()
            }
        }

        val ip = getLocalIpAddress()
        tvWifiUrl.text = "http://$ip:8080/stream"

        val filter = IntentFilter("com.axecast.stream.STATUS_UPDATE")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(statusReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(statusReceiver, filter)
        }

        btnTabWifi.setOnClickListener {
            if (!isStreaming) switchMode("WIFI")
        }

        btnTabRemote.setOnClickListener {
            if (!isStreaming) switchMode("REMOTE")
        }

        btnToggle.setOnClickListener {
            if (!isStreaming) {
                attemptStartStream()
            } else {
                stopStreamService()
            }
        }

        // Check & request all standard permissions at once on launch
        requestInitialPermissions()
    }

    override fun onResume() {
        super.onResume()
        updatePermissionIndicators()
    }

    override fun onDestroy() {
        super.onDestroy()
        try { unregisterReceiver(statusReceiver) } catch (ignored: Exception) {}
    }

    private fun hasUsageAccessPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as? android.app.AppOpsManager ?: return false
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpNoThrow(
                android.app.AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(),
                packageName
            )
        } else {
            appOps.checkOpNoThrow(
                android.app.AppOpsManager.OPSTR_GET_USAGE_STATS,
                android.os.Process.myUid(),
                packageName
            )
        }
        return mode == android.app.AppOpsManager.MODE_ALLOWED
    }

    private fun promptUsageAccessPermission() {
        AlertDialog.Builder(this)
            .setTitle("📱 Enable Active App Detection")
            .setMessage("To automatically detect which app is currently open and filter logs for you, please grant 'Usage Access' permission.\n\nTap 'Open Settings' and switch ON for AxeCast Stream.")
            .setPositiveButton("Open Settings") { _, _ ->
                try {
                    val intent = Intent(android.provider.Settings.ACTION_USAGE_ACCESS_SETTINGS).apply {
                        data = android.net.Uri.parse("package:$packageName")
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    startActivity(intent)
                } catch (e: Exception) {
                    startActivity(Intent(android.provider.Settings.ACTION_USAGE_ACCESS_SETTINGS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    })
                }
            }
            .setNegativeButton("Later", null)
            .show()
    }

    private fun requestInitialPermissions() {
        val permissionsNeeded = ArrayList<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        if (permissionsNeeded.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, permissionsNeeded.toTypedArray(), REQUEST_PERMISSIONS)
        }

        // Also prompt for Usage Access if not granted
        if (!hasUsageAccessPermission()) {
            val hasPrompted = prefs.getBoolean("PROMPTED_USAGE_ACCESS", false)
            if (!hasPrompted) {
                prefs.edit().putBoolean("PROMPTED_USAGE_ACCESS", true).apply()
                promptUsageAccessPermission()
            }
        }

        updatePermissionIndicators()
    }

    private fun updatePermissionIndicators() {
        // 1. Notifications
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val hasNotif = ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            if (hasNotif) {
                tvPermNotif.text = "🟢 Granted"
                tvPermNotif.setTextColor(0xFF22C55E.toInt())
            } else {
                tvPermNotif.text = "🔴 Not Granted"
                tvPermNotif.setTextColor(0xFFEF4444.toInt())
            }
        } else {
            tvPermNotif.text = "🟢 Ready"
            tvPermNotif.setTextColor(0xFF22C55E.toInt())
        }

        // 2. Active App Detection (Usage Access & Logs)
        val hasUsage = hasUsageAccessPermission()
        val hasLogs = checkCallingOrSelfPermission(Manifest.permission.READ_LOGS) == PackageManager.PERMISSION_GRANTED
        if (hasUsage || hasLogs) {
            tvPermLogs.text = "🟢 Granted"
            tvPermLogs.setTextColor(0xFF22C55E.toInt())
        } else {
            tvPermLogs.text = "🟡 Tap to Grant"
            tvPermLogs.setTextColor(0xFFF59E0B.toInt())
        }

        // 3. Package Visibility
        tvPermPkgs.text = "🟢 Ready"
        tvPermPkgs.setTextColor(0xFF22C55E.toInt())
    }

    private fun attemptStartStream() {
        // Enforce Notification permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val hasNotif = ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            if (!hasNotif) {
                Toast.makeText(this, "Notification permission is required for streaming service", Toast.LENGTH_SHORT).show()
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_PERMISSIONS)
                return
            }
        }

        if (activeMode == "REMOTE") {
            val url = etServerUrl.text.toString().trim()
            if (url.isEmpty()) {
                Toast.makeText(this, "Please enter Relay Server URL", Toast.LENGTH_SHORT).show()
                return
            }
            prefs.edit().putString("SERVER_URL", url).apply()
        }

        // Check READ_LOGS permission
        val hasLogs = checkCallingOrSelfPermission(Manifest.permission.READ_LOGS) == PackageManager.PERMISSION_GRANTED
        if (!hasLogs) {
            showReadLogsDialog()
            return
        }

        proceedToCaptureIntent()
    }

    private fun showReadLogsDialog() {
        val adbCmd = "adb shell pm grant com.axecast.stream android.permission.READ_LOGS"
        AlertDialog.Builder(this)
            .setTitle("🛡️ System Logcat Permission")
            .setMessage("To stream system-wide app logs across the entire phone, Android requires one-time READ_LOGS permission.\n\nCommand:\n$adbCmd")
            .setPositiveButton("📋 Copy & Continue") { _, _ ->
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("ADB Command", adbCmd))
                Toast.makeText(this, "Copied ADB command to clipboard", Toast.LENGTH_SHORT).show()
                proceedToCaptureIntent()
            }
            .setNeutralButton("Start Screen Only") { _, _ ->
                proceedToCaptureIntent()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun proceedToCaptureIntent() {
        startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION)
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
            btnTabRemote.setBackgroundColor(0xFF0284C7.toInt())
            btnTabRemote.setTextColor(0xFFFFFFFF.toInt())
            btnTabWifi.setBackgroundColor(0xFF334155.toInt())
            btnTabWifi.setTextColor(0xFF94A3B8.toInt())
            panelWifi.visibility = View.GONE
            panelRemote.visibility = View.VISIBLE
            btnToggle.text = "🌐 Start Remote Share"
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_MEDIA_PROJECTION) {
            if (resultCode == Activity.RESULT_OK && data != null) {
                startStreamService(resultCode, data)
            } else {
                Toast.makeText(this, "Screen capture permission denied", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        updatePermissionIndicators()
    }

    private fun updatePinUi(enabled: Boolean) {
        if (enabled) {
            tvPin.visibility = View.VISIBLE
            if (pin.isNotEmpty()) {
                tvPin.text = "PIN: $pin"
            } else {
                tvPin.text = "PIN: ----"
            }
            tvPin.setTextColor(0xFF38BDF8.toInt())
        } else {
            tvPin.visibility = View.VISIBLE
            tvPin.text = "PIN: OFF (Open)"
            tvPin.setTextColor(0xFF94A3B8.toInt())
        }
    }

    private fun setupResolutionSelector() {
        btnRes360 = findViewById(R.id.btnRes360)
        btnRes480 = findViewById(R.id.btnRes480)
        btnRes720 = findViewById(R.id.btnRes720)
        btnRes1080 = findViewById(R.id.btnRes1080)
        tvActiveResHint = findViewById(R.id.tvActiveResHint)

        selectedResolution = prefs.getInt("STREAM_RESOLUTION", 480)
        updateResolutionUi(selectedResolution)

        btnRes360.setOnClickListener { setResolution(360) }
        btnRes480.setOnClickListener { setResolution(480) }
        btnRes720.setOnClickListener { setResolution(720) }
        btnRes1080.setOnClickListener { setResolution(1080) }
    }

    private fun setResolution(res: Int) {
        selectedResolution = res
        prefs.edit().putInt("STREAM_RESOLUTION", res).apply()
        updateResolutionUi(res)

        if (isStreaming) {
            val intent = Intent("com.axecast.stream.SET_QUALITY").apply {
                putExtra("RESOLUTION", res)
            }
            sendBroadcast(intent)
            Toast.makeText(this, "⚡ Switched to ${res}p Live", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updateResolutionUi(res: Int) {
        val buttons = listOf(btnRes360, btnRes480, btnRes720, btnRes1080)
        val targets = listOf(360, 480, 720, 1080)

        for (i in buttons.indices) {
            val b = buttons[i]
            if (targets[i] == res) {
                b.setBackgroundColor(0xFF0284C7.toInt())
                b.setTextColor(0xFFFFFFFF.toInt())
            } else {
                b.setBackgroundColor(0xFF0F172A.toInt())
                b.setTextColor(0xFF94A3B8.toInt())
            }
        }

        when (res) {
            360 -> tvActiveResHint.text = "360p • Ultra Fast (Lowest Latency)"
            480 -> tvActiveResHint.text = "480p • Low Latency (Recommended)"
            720 -> tvActiveResHint.text = "720p • HD Sharp"
            1080 -> tvActiveResHint.text = "1080p • Full HD"
        }
    }

    private fun startStreamService(resultCode: Int, data: Intent) {
        isStreaming = true
        roomCode = "" // Force generate a brand new fresh code on every start
        pin = ""
        tvRoomCode.text = "--- ---"
        btnToggle.text = "🛑 Stop Stream"
        btnToggle.setBackgroundColor(0xFFDC2626.toInt())

        val serviceIntent = Intent(this, MediaProjectionService::class.java).apply {
            putExtra("RESULT_CODE", resultCode)
            putExtra("DATA_INTENT", data)
            putExtra("MODE", activeMode)
            putExtra("ROOM_CODE", "") // Pass empty to guarantee fresh server-side / client-side code generation
            putExtra("SERVER_URL", etServerUrl.text.toString().trim())
            putExtra("PIN_ENABLED", switchPinLock.isChecked)
            putExtra("RESOLUTION", selectedResolution)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }

    private fun stopStreamService() {
        isStreaming = false
        roomCode = ""
        pin = ""
        btnToggle.text = if (activeMode == "WIFI") "📶 Start Wi-Fi Stream" else "🌐 Start Remote Share"
        btnToggle.setBackgroundColor(0xFF16A34A.toInt())
        tvRoomCode.text = "--- ---"
        tvWifiStatus.text = "⚫ Idle"
        tvRemoteStatus.text = "⚫ Idle"
        updatePinUi(switchPinLock.isChecked)

        val serviceIntent = Intent(this, MediaProjectionService::class.java)
        stopService(serviceIntent)
    }

    private fun getLocalIpAddress(): String {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val addresses = iface.inetAddresses
                while (addresses.hasMoreElements()) {
                    val addr = addresses.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val host = addr.hostAddress
                        if (host != null && (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172."))) {
                            return host
                        }
                    }
                }
            }
        } catch (e: Exception) {}
        return "192.168.1.xxx"
    }
}
