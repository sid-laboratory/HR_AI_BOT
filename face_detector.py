import cv2
import numpy as np
from typing import Dict, List, Any
import time

class FaceDetector:
    def __init__(
        self, 
        min_detection_confidence=0.5, 
        movement_threshold=0.15,  # Increased threshold to be less sensitive
        history_size=10,
        tilt_threshold=0.06  # New parameter specifically for tilt detection
    ):
        # Load the pre-trained Haar cascade classifiers for face detection
        # These XML files are included with OpenCV installation
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        
        # Parameters for head movement detection
        self.prev_face_positions = []
        self.movement_threshold = movement_threshold
        self.tilt_threshold = tilt_threshold
        self.history_size = history_size
        self.last_warning_time = 0
        self.warning_cooldown = 5  # Increased cooldown between warnings (5 seconds)
        
        # Convert min_detection_confidence to scaleFactor (inverse relationship)
        # Lower scale factor = higher confidence but slower detection
        self.scale_factor = 1.1 + (1 - min_detection_confidence) * 0.2
        self.min_neighbors = int(5 * min_detection_confidence)
    
    def process_frame(self, frame) -> Dict[str, Any]:
        """
        Process a frame to detect faces and head movements (specifically left/right tilts).
        
        Args:
            frame: The video frame to process
            
        Returns:
            Dict containing:
                - faces_count: Number of faces detected
                - tilt_detected: Whether significant head tilt was detected
                - tilt_direction: Direction of tilt ("left", "right", or None)
                - warnings: List of warning messages
        """
        if frame is None:
            return {"faces_count": 0, "tilt_detected": False, "tilt_direction": None, "warnings": ["No frame received"]}
        
        # Convert to grayscale for Haar cascade detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        warnings = []
        faces_count = 0
        tilt_detected = False
        tilt_direction = None
        
        # Detect faces in the image
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=(30, 30)
        )
        
        # Process face detection results
        if len(faces) > 0:
            faces_count = len(faces)
            
            # Check for multiple faces
            if faces_count > 1:
                warnings.append(f"Multiple faces detected ({faces_count} faces)")
        else:
            warnings.append("No face detected")
            
        # Track face positions for tilt detection
        current_positions = []
        for (x, y, w, h) in faces:
            # Use center of face as reference point for head position
            center_x = x + w/2
            center_y = y + h/2
            face_size = w * h  # Used to normalize movement
            
            # Store position with normalized coordinates (0-1 range)
            height, width = frame.shape[:2]
            norm_x = center_x / width
            norm_y = center_y / height
            norm_size = face_size / (width * height)
            
            # Calculate face angle/orientation if possible 
            # This is a simple approximation - using x-coordinate changes to detect tilt
            current_positions.append((norm_x, norm_y, norm_size))
            
            # Validate face detection with eye detection for better accuracy
            roi_gray = gray[y:y+h, x:x+w]
            eyes = self.eye_cascade.detectMultiScale(roi_gray)
            if len(eyes) == 0:
                # No eyes detected in the face region, might be a false positive
                warnings.append("Face detected but no eyes visible")
        
        # Detect head tilt (left/right only)
        if current_positions and self.prev_face_positions:
            for i, current_pos in enumerate(current_positions):
                if i < len(self.prev_face_positions):
                    prev_pos = self.prev_face_positions[i]
                    
                    # Focus only on horizontal (x) movement for tilt detection
                    # Ignore vertical (y) movements and size changes
                    x_shift = current_pos[0] - prev_pos[0]
                    
                    # Only detect significant left/right movements
                    if abs(x_shift) > self.tilt_threshold:
                        tilt_detected = True
                        tilt_direction = "left" if x_shift > 0 else "right"
                        
                        # Add cooldown between warnings to prevent spamming
                        current_time = time.time()
                        if current_time - self.last_warning_time > self.warning_cooldown:
                            warnings.append(f"Head tilt detected ({tilt_direction})")
                            self.last_warning_time = current_time
        
        # Update position history
        self.prev_face_positions = current_positions
        if len(self.prev_face_positions) > self.history_size:
            self.prev_face_positions = self.prev_face_positions[-self.history_size:]
        
        return {
            "faces_count": faces_count,
            "tilt_detected": tilt_detected,
            "tilt_direction": tilt_direction,
            "warnings": warnings
        }