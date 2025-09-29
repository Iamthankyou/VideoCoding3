# Các Tool và Tham Số Tốc Độ trong File Cấu Hình Random Access VVC

## Tổng quan

VVC Software VTM cung cấp nhiều tool và tham số có thể điều chỉnh để tối ưu hóa tốc độ mã hóa trong chế độ Random Access. Các tham số này được chia thành các nhóm chính:

## 1. Motion Search (Tìm kiếm chuyển động)

### FastSearch
- **Mô tả**: Chọn thuật toán tìm kiếm chuyển động
- **Giá trị**: 
  - `0`: Full search (tìm kiếm toàn bộ, chậm nhất nhưng chính xác nhất)
  - `1`: TZ search (Test Zone search, nhanh hơn)
- **Ảnh hưởng**: Giảm từ 1 xuống 0 sẽ tăng tốc độ nhưng giảm chất lượng

### SearchRange
- **Mô tả**: Phạm vi tìm kiếm chuyển động
- **Giá trị mặc định**: `384`
- **Ảnh hưởng**: Giảm giá trị này sẽ tăng tốc độ nhưng có thể bỏ lỡ chuyển động lớn

### ASR (Adaptive Search Range)
- **Mô tả**: Tìm kiếm chuyển động thích ứng
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tối ưu hóa phạm vi tìm kiếm

### MinSearchWindow
- **Mô tả**: Kích thước cửa sổ tìm kiếm tối thiểu
- **Giá trị mặc định**: `96`
- **Ảnh hưởng**: Giảm sẽ tăng tốc độ

### BipredSearchRange
- **Mô tả**: Phạm vi tìm kiếm cho dự đoán hai chiều
- **Giá trị mặc định**: `4`
- **Ảnh hưởng**: Giảm sẽ tăng tốc độ

### HadamardME
- **Mô tả**: Sử dụng đo lường Hadamard cho ME phân số
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

## 2. Fast Encoder Tools (Công cụ mã hóa nhanh)

### FEN (Fast Encoder Decision)
- **Mô tả**: Quyết định mã hóa nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ đáng kể

### FDM (Fast Decision for Merge RD cost)
- **Mô tả**: Quyết định nhanh cho chi phí RD merge
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### LCTUFast
- **Mô tả**: Mã hóa CTU nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

## 3. Coding Tools (Công cụ mã hóa)

### MTS (Multiple Transform Selection)
- **Mô tả**: Lựa chọn biến đổi đa dạng
- **Giá trị**: 
  - `0`: Tắt
  - `1`: Bật với DCT-II và DST-VII
  - `3`: Bật với tất cả biến đổi
  - `4`: Implicit MTS (nhanh hơn)
- **Ảnh hưởng**: Giảm từ 3 xuống 4 hoặc 0 sẽ tăng tốc độ

### SBT (Sub-Block Transform)
- **Mô tả**: Biến đổi khối con
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### LFNST (Low-Frequency Non-Separable Transform)
- **Mô tả**: Biến đổi không tách biệt tần số thấp
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### ISP (Intra Sub-Partitions)
- **Mô tả**: Phân vùng con nội khung
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### MMVD (Merge Mode with Motion Vector Difference)
- **Mô tả**: Chế độ merge với độ khác biệt vector chuyển động
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### Affine
- **Mô tả**: Dự đoán affine
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### SbTMVP (Sub-block Temporal Motion Vector Prediction)
- **Mô tả**: Dự đoán vector chuyển động thời gian khối con
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### BIO (Bidirectional Optical Flow)
- **Mô tả**: Dòng quang học hai chiều
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### CIIP (Combined Inter-Intra Prediction)
- **Mô tả**: Dự đoán kết hợp nội-ngoại khung
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### Geo (Geometric partitioning)
- **Mô tả**: Phân vùng hình học
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### IBC (Intra Block Copy)
- **Mô tả**: Sao chép khối nội
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### PROF (Prediction Refinement with Optical Flow)
- **Mô tả**: Tinh chỉnh dự đoán với dòng quang học
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

## 4. Fast Tools (Công cụ nhanh)

### PBIntraFast
- **Mô tả**: Mã hóa nội nhanh cho PB
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### ISPFast
- **Mô tả**: ISP nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### FastMrg
- **Mô tả**: Merge nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### AMaxBT
- **Mô tả**: Tối đa BT thích ứng
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### FastMIP
- **Mô tả**: MIP nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### FastLFNST
- **Mô tả**: LFNST nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### FastLocalDualTreeMode
- **Mô tả**: Chế độ cây đôi cục bộ nhanh
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

## 5. Partitioning và MTT (Multi-Type Tree)

### MaxMTTHierarchyDepth
- **Mô tả**: Độ sâu tối đa của cây đa loại
- **Giá trị mặc định**: `3`
- **Ảnh hưởng**: Giảm xuống `2` hoặc `1` sẽ tăng tốc độ đáng kể

### MaxMTTHierarchyDepthISliceL
- **Mô tả**: Độ sâu MTT cho I-slice luma
- **Giá trị mặc định**: `3`
- **Ảnh hưởng**: Giảm sẽ tăng tốc độ

### MaxMTTHierarchyDepthISliceC
- **Mô tả**: Độ sâu MTT cho I-slice chroma
- **Giá trị mặc định**: `3`
- **Ảnh hưởng**: Giảm sẽ tăng tốc độ

### CTUSize
- **Mô tả**: Kích thước CTU
- **Giá trị mặc định**: `128`
- **Ảnh hưởng**: Giảm xuống `64` sẽ tăng tốc độ

## 6. Merge Candidates

### MaxNumMergeCand
- **Mô tả**: Số lượng ứng viên merge tối đa
- **Giá trị mặc định**: `6`
- **Ảnh hưởng**: Giảm xuống `5` hoặc `4` sẽ tăng tốc độ

### MaxMergeRdCandNumTotal
- **Mô tả**: Tổng số ứng viên merge cho RD
- **Giá trị mặc định**: `7` (performance) hoặc `11` (high performance)
- **Ảnh hưởng**: Giảm sẽ tăng tốc độ

## 7. Encoder Optimization Tools

### AffineAmvrEncOpt
- **Mô tả**: Tối ưu hóa encoder cho AMVR affine
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### EncDbOpt
- **Mô tả**: Áp dụng deblocking trong RDO
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Tắt sẽ tăng tốc độ

### MTTSkipping
- **Mô tả**: Bỏ qua MTT
- **Giá trị**: `0` (tắt) hoặc `1` (bật)
- **Ảnh hưởng**: Bật sẽ tăng tốc độ

### SplitPredictAdaptMode
- **Mô tả**: Chế độ thích ứng dự đoán phân chia
- **Giá trị**: `0`, `1`, hoặc `2`
- **Ảnh hưởng**: Tăng giá trị sẽ tăng tốc độ

## 8. Cấu hình Reduced Runtime

VTM cung cấp 3 cấu hình giảm thời gian chạy:

### Reduced Runtime 1 (Giảm ít nhất)
```cfg
# Reduce MTT depth
MaxMTTHierarchyDepth: 2
```

### Reduced Runtime 2 (Giảm trung bình)
```cfg
# Reduce MTT depth
MaxMTTHierarchyDepth : 2
MaxMTTHierarchyDepthISliceL : 2

# Use implicit MTS instead of explicit MTS
MTS: 4

# Reduce number of merge candidates
MaxNumMergeCand: 5

# Reduce number of merge candidates for RD
MaxMergeRdCandNumTotal : 5
MergeRdCandQuotaGpm : 5

# Tool configuration
UseNonLinearAlfLuma : 0
AllowDisFracMMVD : 0

# Partitioning encoder configuration
SplitPredictAdaptMode : 2
ContentBasedFastQtbt : 1

# Faster encoder configurations
AdaptBypassAffineMe : 1
```

### Reduced Runtime 3 (Giảm nhiều nhất)
```cfg
# Use smaller CTUs
CTUSize: 64

# Reduce MTT depth
MaxMTTHierarchyDepth : 1
MaxMTTHierarchyDepthISliceL : 2
MaxMTTHierarchyDepthISliceC : 1 

# Reduce Max{B,T}TNonISlice
MaxTTNonISlice : 32
MaxBTNonISlice : 64

# Use implicit MTS instead of explicit MTS
MTS: 4

# Reduce number of merge candidates
MaxNumMergeCand: 5

# Reduce number of merge candidates for RD
MaxMergeRdCandNumTotal : 4
MergeRdCandQuotaGpm : 4

# Tool configuration
UseNonLinearAlfLuma : 0
AllowDisFracMMVD : 0
AffineAmvr : 0

# Partitioning encoder configuration
SplitPredictAdaptMode : 2
ContentBasedFastQtbt : 1

# Faster encoder configurations
AdaptBypassAffineMe : 1
ISPFast : 1
FastMIP : 1
AffineAmvrEncOpt : 0
```

## 9. Cấu hình High Performance

File `cfg/alternative_high_perf/encoder_randomaccess_vtm_perf.cfg` cung cấp hiệu suất mã hóa cao hơn nhưng thời gian chạy lâu hơn:

- `FEN: 0` (tắt fast encoder decision)
- `FDM: 0` (tắt fast decision for merge)
- `MaxMTTHierarchyDepthISliceL: 4` (tăng độ sâu MTT)
- `MTS: 3` (bật tất cả biến đổi)
- `MaxMergeRdCandNumTotal: 11` (tăng số ứng viên merge)

## 10. Khuyến nghị sử dụng

### Cho tốc độ nhanh nhất:
1. Sử dụng `reduced_runtime3.cfg` làm add-on
2. Tắt các tool: `SBT`, `LFNST`, `ISP`, `MMVD`, `Affine`, `BIO`, `CIIP`, `Geo`, `PROF`
3. Giảm `MaxMTTHierarchyDepth` xuống `1`
4. Giảm `CTUSize` xuống `64`
5. Giảm `MaxNumMergeCand` xuống `4`

### Cho cân bằng tốc độ/chất lượng:
1. Sử dụng `reduced_runtime2.cfg` làm add-on
2. Giữ các tool cơ bản: `MTS`, `SAO`, `ALF`
3. Giảm `MaxMTTHierarchyDepth` xuống `2`
4. Giảm `MaxNumMergeCand` xuống `5`

### Cho chất lượng cao nhất:
1. Sử dụng `encoder_randomaccess_vtm_perf.cfg`
2. Bật tất cả các tool
3. Tăng `MaxMTTHierarchyDepth` lên `4`
4. Tăng `MaxMergeRdCandNumTotal` lên `11`

## 11. Cách áp dụng

Để sử dụng các cấu hình reduced runtime:

```bash
# Sử dụng cấu hình cơ bản + reduced runtime
./EncoderApp -c cfg/encoder_randomaccess_vtm.cfg -c cfg/alternative-addon/reduced_runtime3.cfg

# Sử dụng cấu hình high performance
./EncoderApp -c cfg/alternative_high_perf/encoder_randomaccess_vtm_perf.cfg
```

## 12. Lưu ý quan trọng

- Việc tắt các tool sẽ giảm hiệu suất nén nhưng tăng tốc độ mã hóa
- Các tham số này có thể ảnh hưởng đến tính tương thích với decoder
- Nên test trên một số frame trước khi áp dụng cho toàn bộ video
- Các tham số có thể thay đổi theo phiên bản VTM
