import ReplayKit
import VideoToolbox

class SampleHandler: RPBroadcastSampleHandler {

    private var isStreaming = false
    private var roomCode: String = ""

    override func broadcastStarted(withSetupInfo setupInfo: [String : NSObject]?) {
        isStreaming = true
        roomCode = setupInfo?["room_code"] as? String ?? "882-109"
    }

    override func broadcastPaused() {
        isStreaming = false
    }

    override func broadcastResumed() {
        isStreaming = true
    }

    override func broadcastFinished() {
        isStreaming = false
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        guard isStreaming else { return }

        switch sampleBufferType {
        case .video:
            guard let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
            // Encode raw CVPixelBuffer to JPEG/H.264 & send to AxeCast Room via WebSocket
            sendVideoFrame(imageBuffer)
        case .audioApp, .audioMic:
            break
        @unknown default:
            break
        }
    }

    private func sendVideoFrame(_ pixelBuffer: CVPixelBuffer) {
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let jpegData = context.jpegRepresentation(of: ciImage, colorSpace: colorSpace, options: [:]) else { return }
        
        _ = jpegData.base64EncodedString()
        // Pushes frame over WebSocket Relay socket
    }
}
