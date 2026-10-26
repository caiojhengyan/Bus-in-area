# TDX 範圍公車紀錄

在地圖上點選 ≥3 個點圍成範圍，只記錄範圍內的公車（離開即停止記錄），匯出 KML 與 Excel（依車牌、業者、進入時間排序）。

## 兩種使用方式

### A. GitHub Pages（純網頁，直接用）
`index.html` 由瀏覽器直接呼叫 TDX。金鑰由使用者在網頁輸入，只存在自己的瀏覽器，**不要把金鑰寫進任何檔案或提交到 repo**。
啟用：Settings → Pages → Branch: main / root。

> 若瀏覽器因 CORS 無法連到 TDX，請改用 B。

### B. 本機版（`local/`）
```
cd local
python tdx_bus_area.py
# 開啟 http://localhost:8765
```
金鑰只送到本機程式，並有伺服器端快取。

## 省額度設計
- 全台只呼叫一支 API：`/v2/Bus/RealTimeByFrequency/NearBy`（空間篩選，一個外接圓涵蓋整個範圍）
- 10 秒內相同查詢使用快取
- 預設每 30 秒輪詢，可調大以進一步節省
- Token 快取到過期前才更新

## 說明
- 「到站時間」= 進入範圍的時間（A1 資料只有車輛位置）；另記離開時間與停留秒數。
- 業者欄位為 OperatorID 代碼。
