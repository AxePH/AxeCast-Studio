package com.axecast.stream

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import kotlin.random.Random

class MainActivity : AppCompatActivity() {

    private val REQUEST_MEDIA_PROJECTION = 1001
    private lateinit var projectionManager: MediaProjectionManager
    private var isStreaming = false
    private var roomCode = ""
    private var pin = ""

    private lateinit var tvRoomCode: TextView
    private lateinit var tvPin: TextView
    private lateinit var btnToggle: Button
    private lateinit var tvStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

        tvRoomCode = findViewById(R.id.tvRoomCode)
        tvPin = findViewById(R.id.tvPin)
        btnToggle = findViewById(R.id.btnToggle)
        tvStatus = findViewById(R.id.tvStatus)

        btnToggle.setOnClickListener {
            if (!isStreaming) {
                startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION)
            } else {
                stopStreamService()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_MEDIA_PROJECTION && resultCode == Activity.RESULT_OK && data != null) {
            val c1 = Random.nextInt(100, 999)
            val c2 = Random.nextInt(100, 999)
            roomCode = "$c1-$c2"
            pin = Random.nextInt(1000, 9999).toString()

            tvRoomCode.text = roomCode
            tvPin.text = "PIN: $pin"
            tvStatus.text = "🟢 Live Streaming"
            btnToggle.text = "⏹ Stop Broadcast"
            isStreaming = true

            val serviceIntent = Intent(this, MediaProjectionService::class.java).apply {
                putExtra("RESULT_CODE", resultCode)
                putExtra("DATA_INTENT", data)
                putExtra("ROOM_CODE", roomCode)
                putExtra("PIN", pin)
            }
            startForegroundService(serviceIntent)
        } else {
            Toast.makeText(this, "Screen capture permission required", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopStreamService() {
        stopService(Intent(this, MediaProjectionService::class.java))
        isStreaming = false
        tvStatus.text = "⚫ Idle"
        btnToggle.text = "🔴 Start Broadcast"
        tvRoomCode.text = "--- ---"
        tvPin.text = "PIN: ----"
    }
}
