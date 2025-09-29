# MultiView Support trong VVC Software VTM

## Tổng quan

VVC Software VTM hỗ trợ đầy đủ MultiView cho video 3D thông qua hai loại SEI (Supplemental Enhancement Information) message chính:

1. **SEIMultiviewAcquisitionInfo** - Thông tin thu thập đa góc nhìn
2. **SEIMultiviewViewPosition** - Vị trí góc nhìn đa góc nhìn

## Cách MultiView hoạt động

### 1. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────┐
│                    VVC MultiView System                     │
├─────────────────────────────────────────────────────────────┤
│  Input: Multiple Camera Views (3D Video)                    │
│  ├── View 0 (Left Eye)                                      │
│  ├── View 1 (Right Eye)                                     │
│  ├── View 2 (Additional View)                               │
│  └── ...                                                     │
├─────────────────────────────────────────────────────────────┤
│  Encoder Processing                                          │
│  ├── Camera Calibration (SEIMultiviewAcquisitionInfo)       │
│  ├── View Position (SEIMultiviewViewPosition)               │
│  ├── Video Encoding (H.266/VVC)                             │
│  └── SEI Message Generation                                  │
├─────────────────────────────────────────────────────────────┤
│  Bitstream Output                                            │
│  ├── VVC Video Data                                          │
│  ├── SEI: MultiviewAcquisitionInfo                          │
│  └── SEI: MultiviewViewPosition                             │
├─────────────────────────────────────────────────────────────┤
│  Decoder Processing                                          │
│  ├── Video Decoding (H.266/VVC)                             │
│  ├── SEI Message Parsing                                     │
│  ├── Camera Parameter Recovery                               │
│  └── 3D Scene Reconstruction                                 │
├─────────────────────────────────────────────────────────────┤
│  Output: 3D Video with Depth Information                     │
│  ├── Depth Map Generation                                    │
│  ├── View Synthesis                                          │
│  ├── Stereo Matching                                         │
│  └── 3D Rendering                                            │
└─────────────────────────────────────────────────────────────┘
```

### 2. Tham số Camera Calibration

#### Tham số nội tại (Intrinsic Parameters)
- **Focal Length (fx, fy)**: Tiêu cự của camera, xác định độ zoom
  - fx: tiêu cự theo trục x
  - fy: tiêu cự theo trục y
- **Principal Point (cx, cy)**: Điểm chính của camera, thường là tâm của ảnh
- **Skew Factor (s)**: Hệ số nghiêng, mô tả độ nghiêng của các pixel

#### Tham số ngoại tại (Extrinsic Parameters)
- **Rotation Matrix R[3][3]**: Ma trận xoay 3x3, mô tả hướng của camera
- **Translation Vector T[3]**: Vector dịch chuyển 3x1, mô tả vị trí của camera

### 3. Quy trình mã hóa

#### Bước 1: Khởi tạo SEI Messages
```cpp
// Khởi tạo thông tin thu thập đa góc nhìn
SEIMultiviewAcquisitionInfo *seiMAI = new SEIMultiviewAcquisitionInfo;
m_seiEncoder.initSEIMultiviewAcquisitionInfo(seiMAI);

// Khởi tạo vị trí góc nhìn
SEIMultiviewViewPosition *seiMVP = new SEIMultiviewViewPosition;
m_seiEncoder.initSEIMultiviewViewPosition(seiMVP);
```

#### Bước 2: Thiết lập tham số Camera
```cpp
// Đọc cấu hình từ file config
sei->m_maiIntrinsicParamFlag = m_pcCfg->getMaiSEIIntrinsicParamFlag();
sei->m_maiExtrinsicParamFlag = m_pcCfg->getMaiSEIExtrinsicParamFlag();
sei->m_maiNumViewsMinus1 = m_pcCfg->getMaiSEINumViewsMinus1();

// Thiết lập tham số nội tại
sei->m_maiPrecFocalLength = m_pcCfg->getMaiSEIPrecFocalLength();
sei->m_maiPrecPrincipalPoint = m_pcCfg->getMaiSEIPrecPrincipalPoint();
sei->m_maiPrecSkewFactor = m_pcCfg->getMaiSEIPrecSkewFactor();
```

#### Bước 3: Mã hóa SEI Messages
```cpp
// Mã hóa thông tin thu thập đa góc nhìn
xWriteSEIMultiviewAcquisitionInfo(sei);

// Mã hóa vị trí góc nhìn
xWriteSEIMultiviewViewPosition(sei);
```

### 4. Quy trình giải mã

#### Bước 1: Parse SEI Messages
```cpp
// Parse thông tin thu thập đa góc nhìn
xParseSEIMultiviewAcquisitionInfo(sei, payloadSize, outputStream);

// Parse vị trí góc nhìn
xParseSEIMultiviewViewPosition(sei, payloadSize, outputStream);
```

#### Bước 2: Khôi phục tham số Camera
```cpp
// Khôi phục tham số nội tại
for (int i = 0; i <= numViewsMinus1; i++) {
    // Khôi phục focal length
    double fx = reconstructValue(sign[i], exponent[i], mantissa[i]);
    double fy = reconstructValue(sign[i], exponent[i], mantissa[i]);
    
    // Khôi phục principal point
    double cx = reconstructValue(sign[i], exponent[i], mantissa[i]);
    double cy = reconstructValue(sign[i], exponent[i], mantissa[i]);
    
    // Khôi phục skew factor
    double s = reconstructValue(sign[i], exponent[i], mantissa[i]);
}

// Khôi phục tham số ngoại tại
for (int i = 0; i <= numViewsMinus1; i++) {
    // Khôi phục ma trận xoay R[3][3]
    for (int j = 0; j < 3; j++) {
        for (int k = 0; k < 3; k++) {
            R[i][j][k] = reconstructValue(sign[i][j][k], exponent[i][j][k], mantissa[i][j][k]);
        }
    }
    
    // Khôi phục vector dịch chuyển T[3]
    for (int j = 0; j < 3; j++) {
        T[i][j] = reconstructValue(sign[i][j], exponent[i][j], mantissa[i][j]);
    }
}
```

### 5. Ứng dụng trong 3D Video

#### Depth Map Generation
```cpp
// Sử dụng tham số camera để tính toán depth map
void generateDepthMap(const SEIMultiviewAcquisitionInfo& mai) {
    // Tính toán disparity từ stereo images
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            // Sử dụng focal length và baseline để tính depth
            double disparity = computeDisparity(leftImage, rightImage, x, y);
            double depth = (mai.focalLength * mai.baseline) / disparity;
            depthMap[y][x] = depth;
        }
    }
}
```

#### View Synthesis
```cpp
// Tạo góc nhìn mới từ các góc nhìn có sẵn
void synthesizeView(const SEIMultiviewAcquisitionInfo& mai, 
                   const std::vector<cv::Mat>& inputViews,
                   cv::Mat& outputView) {
    // Sử dụng tham số camera để warp và blend các góc nhìn
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            // Tính toán vị trí tương ứng trong các góc nhìn input
            std::vector<cv::Point2f> correspondences;
            for (int view = 0; view < inputViews.size(); view++) {
                cv::Point2f point = warpPoint(x, y, mai.R[view], mai.T[view]);
                correspondences.push_back(point);
            }
            
            // Blend các pixel từ các góc nhìn
            outputView.at<cv::Vec3b>(y, x) = blendPixels(correspondences, inputViews);
        }
    }
}
```

### 6. File cấu hình

#### multiview_acquisition_info.cfg
```ini
#======== Multiview Acquisition Information SEI message =====================
SEIMAIEnabled                         : 1                    # Bật/tắt SEI message
SEIMAIIntrinsicParamFlag              : 1                    # Có thông tin nội tại
SEIMAIExtrinsicParamFlag              : 1                    # Có thông tin ngoại tại
SEIMAINumViewsMinus1                  : 1                    # 2 góc nhìn (0, 1)
SEIMAIIntrinsicParamsEqualFlag        : 1                    # Các góc nhìn có cùng tham số nội tại
SEIMAIPrecFocalLength                 : 31                   # Độ chính xác focal length
SEIMAIPrecPrincipalPoint              : 31                   # Độ chính xác principal point
SEIMAIPrecSkewFactor                  : 31                   # Độ chính xác skew factor
SEIMAIPrecRotationParam               : 31                   # Độ chính xác rotation
SEIMAIPrecTranslationParam            : 31                   # Độ chính xác translation
```

#### multiview_view_position.cfg
```ini
#======== Multiview View Position SEI message =====================
SEIMVPEnabled                         : 1                    # Bật/tắt SEI message
SEIMVPNumViewsMinus1                  : 1                    # 2 góc nhìn
SEIMVPViewPosition                    : 0 1                  # Vị trí góc nhìn 0 và 1
```

### 7. Lợi ích của MultiView trong VVC

1. **Hiệu quả bitrate**: Chia sẻ thông tin camera calibration giữa các góc nhìn
2. **Chất lượng 3D**: Cung cấp thông tin chính xác cho depth estimation
3. **View synthesis**: Cho phép tạo góc nhìn mới từ các góc nhìn có sẵn
4. **Stereo matching**: Hỗ trợ tính toán disparity và depth map
5. **3D reconstruction**: Khôi phục thông tin 3D từ video 2D

### 8. Các file chính trong codebase

- `source/Lib/CommonLib/SEI.h` - Định nghĩa các class SEI
- `source/Lib/DecoderLib/SEIread.cpp` - Parse SEI messages
- `source/Lib/EncoderLib/SEIwrite.cpp` - Write SEI messages
- `source/Lib/EncoderLib/SEIEncoder.cpp` - Khởi tạo SEI messages
- `cfg/sei_vui/multiview_acquisition_info.cfg` - Cấu hình thông tin thu thập
- `cfg/sei_vui/multiview_view_position.cfg` - Cấu hình vị trí góc nhìn

### 9. Kết luận

MultiView support trong VVC Software VTM cung cấp một framework hoàn chỉnh cho việc mã hóa và giải mã video 3D. Thông qua các SEI messages, hệ thống có thể:

- Mã hóa thông tin camera calibration một cách hiệu quả
- Hỗ trợ nhiều góc nhìn với cấu hình linh hoạt
- Cho phép tái tạo 3D scene và view synthesis
- Tương thích với chuẩn VVC/H.266

Điều này làm cho VVC trở thành một chuẩn mã hóa video mạnh mẽ cho các ứng dụng 3D và immersive media.
