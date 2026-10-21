# 便利帶會員專網：GCP 週間定時自動執行

**部署方式**：程式碼 push 到 GitHub 的 `main` 分支 → **Cloud Build** 自動建置並部署 → 更新 **Cloud Run Job**。
**執行方式**：**Cloud Scheduler**（週一到週五 13:30，台北時區）→ 觸發 Cloud Run Job（asia-east1 彰化）→ Playwright 登入並執行任務。
帳號密碼存在 **Secret Manager**，不會出現在程式碼或 GitHub 上。

**任務內容**：登入 → 點「呼叫快遞」→ 在「小件」欄位填入 `30` → 按「呼叫」。

**國定假日自動跳過**：程式每次啟動時，會先讀取政府辦公日曆（[ruyut/TaiwanCalendar](https://github.com/ruyut/TaiwanCalendar)，資料來自行政院人事行政總處），如果當天放假，就直接結束不執行。
- 如果行事曆讀取失敗，會改成只用「週六日不執行」來判斷，並在記錄中留下警告。
- 2026 年沒有補班的週六，所以排程只設週一到週五。如果之後有補班日，把排程改成 `30 13 * * 1-6`，程式會自動判斷哪些週六要上班。

| 檔案 | 用途 |
|---|---|
| `main.py` | 登入 + 任務腳本；任務內容寫在 `do_task()` |
| `Dockerfile` | 使用 Playwright 官方映像（Ubuntu 26.04 / Python 3.14）打包；升級 Playwright 時，這裡和 `pyproject.toml` 的版本要一起改 |
| `cloudbuild.yaml` | Cloud Build 的步驟：建置映像 → 推到 Artifact Registry → 部署 Cloud Run Job |
| `run-local.ps1` | 本機測試用：會開出瀏覽器視窗執行一次 |
| `pyproject.toml`、`uv.lock`、`.python-version` | 本機的 uv 環境設定，雲端不會用到 |

---

# 一次性設定

以下標示 **Cloud Shell** 的指令，請在 GCP 主控台右上角的 `>_` 圖示開啟 Cloud Shell 後執行。它是網頁版終端機，已經內建 gcloud，電腦上不用另外安裝任何東西。

## 步驟 1：啟用 API、建立映像存放區和服務帳戶（Cloud Shell）

先確認 Cloud Shell 提示字元顯示的是正確的專案。如果不是，先執行 `gcloud config set project 你的專案ID`。

```bash
PROJECT=$(gcloud config get-value project)
REGION=asia-east1
BOT=courier-bot@$PROJECT.iam.gserviceaccount.com
DEPLOYER=courier-deployer@$PROJECT.iam.gserviceaccount.com

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

# 存放 Docker 映像的地方
gcloud artifacts repositories create call-courier --repository-format=docker --location=$REGION

# courier-bot：執行任務用；courier-deployer：給 Cloud Build 部署用
gcloud iam service-accounts create courier-bot --display-name="call-courier 執行"
gcloud iam service-accounts create courier-deployer --display-name="call-courier 部署"

# courier-bot 可以被排程觸發
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$BOT --role=roles/run.invoker --condition=None

# courier-deployer 可以推映像、部署 Cloud Run Job、寫建置記錄，並以 courier-bot 身分部署
for ROLE in roles/artifactregistry.writer roles/run.developer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$DEPLOYER --role=$ROLE --condition=None
done
gcloud iam service-accounts add-iam-policy-binding $BOT --member=serviceAccount:$DEPLOYER --role=roles/iam.serviceAccountUser
```

> 如果 Cloud Shell 斷線重連，要重新執行前四行的變數設定。

## 步驟 2：存放帳號密碼（請自己在主控台操作）

1. 打開 https://console.cloud.google.com/security/secret-manager
2. 按「建立密鑰」，名稱填 `member-username`，值填登入帳號，然後按建立
3. 再建立一個：名稱填 `member-password`，值填密碼

接著授權 courier-bot 讀取這兩個密鑰（Cloud Shell）：

```bash
gcloud secrets add-iam-policy-binding member-username --member=serviceAccount:$BOT --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding member-password --member=serviceAccount:$BOT --role=roles/secretmanager.secretAccessor
```

## 步驟 3：把程式碼 push 到 GitHub（你的電腦）

1. 在 GitHub 建立一個新的 repo，例如 `call-courier`。建議設為 **Private**，而且建立時**不要**勾選加入 README。
2. 在 PowerShell 執行（`你的帳號` 換成你的 GitHub 帳號）：

```powershell
cd D:\project\call-courier
git init -b main
git add .
git commit -m "便利帶呼叫快遞自動化"
git remote add origin https://github.com/你的帳號/call-courier.git
git push -u origin main
```

## 步驟 4：建立 Cloud Build 觸發條件（主控台）

1. 打開 https://console.cloud.google.com/cloud-build/triggers ，上方的區域選 **asia-east1**
2. 按「連結存放區」→ 選 **GitHub** → 依照畫面授權 Google Cloud Build GitHub App，並選擇 `call-courier` repo
3. 按「建立觸發條件」，設定如下：
   - 名稱：`call-courier-deploy`
   - 事件：**推送至分支**
   - 分支：`^main$`
   - 設定：**Cloud Build 設定檔（YAML 或 JSON）**，位置：存放區，路徑：`/cloudbuild.yaml`
   - 服務帳戶：選 `courier-deployer@...`
4. 建立完成後，在觸發條件清單中按「**執行**」，手動部署第一次。之後只要 push 就會自動部署。

到「記錄」頁面可以看建置進度，第一次大約需要 3～5 分鐘。

## 步驟 5：測試執行，不會真的叫快遞（主控台）

1. 打開 https://console.cloud.google.com/run/jobs ，點 `call-courier`
2. 按「**執行**」旁邊的選單 →「**使用覆寫值執行**」
3. 新增兩個環境變數：`DRY_RUN` = `true`、`FORCE_RUN` = `true`，然後執行
4. 到「記錄」分頁，應該依序看到：`登入成功` → `已點選「呼叫快遞」` → `「小件」已填入：30` → `DRY_RUN=true，不按「呼叫」` → `任務完成`

- `DRY_RUN=true`：只填欄位，不按「呼叫」。
- `FORCE_RUN=true`：略過假日判斷，假日也能測試。
- 覆寫值只對這一次執行有效，不會影響排程。

> ⚠️ 不加 `DRY_RUN` 直接按「執行」，會**真的叫快遞**。

## 步驟 6：設定週間 13:30 自動執行（Cloud Shell）

```bash
gcloud scheduler jobs create http call-courier-weekday --location=$REGION --schedule="30 13 * * 1-5" --time-zone="Asia/Taipei" --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/call-courier:run" --http-method=POST --oauth-service-account-email=$BOT
```

設定完成。之後每個工作日 13:30 會自動執行，可以到 Cloud Run → `call-courier` →「記錄」查看結果。

---

# 日常使用

## 本機測試

需要先安裝 [uv](https://docs.astral.sh/uv/)。Python 版本固定在 3.14（見 `.python-version`），和雲端映像一致。

**執行測試**（會開出瀏覽器視窗，只填欄位、不按「呼叫」）：

```powershell
cd D:\project\call-courier
powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```

- 第一次執行時，uv 會自動建立 `.venv`，並下載 Chromium（大約 150 MB）。
- 程式會詢問帳號和密碼。輸入密碼時畫面不會顯示，也不會留在指令紀錄裡。
- 每個動作會放慢 0.5 秒，方便你看清楚；全部完成後，在 PowerShell 按 Enter 才會關閉瀏覽器。
- 如果失敗，當下畫面會存成 `error.png`。
- 要**真的叫快遞**，就在指令最後加上 `-Real`。

## 修改程式

改完 `main.py` 之後，在 PowerShell 執行：

```powershell
git add .
git commit -m "說明這次改了什麼"
git push
```

Cloud Build 會自動部署，排程不用重設。部署進度可以到 Cloud Build →「記錄」查看。

- 要改小件的數量：修改 `main.py` 最上方的 `SMALL_PARCELS`。
- 要加其他步驟：可以用 Playwright 錄製操作：
  ```powershell
  uv run playwright codegen https://member.25431010.tw/auth/login
  ```
  請**自己**登入並操作一次，然後把「登入之後」那幾行程式碼貼進 `do_task()`。錄到的程式碼裡有帳號密碼，那幾行**不要**貼過去，更**不要** push 到 GitHub。

## 常用調整

| 想做的事 | 在哪裡改 |
|---|---|
| 改執行時間 | 主控台 → Cloud Scheduler → `call-courier-weekday` → 編輯 → 修改頻率，例如 `35 13 * * 1-5` |
| 暫停或恢復排程 | 主控台 → Cloud Scheduler → 勾選 `call-courier-weekday` →「暫停」或「繼續」 |
| 更新密碼 | 主控台 → Secret Manager → `member-password` →「新增版本」 |

## 疑難排解

- **Cloud Build 失敗，訊息有 `PERMISSION_DENIED`**：確認觸發條件的服務帳戶是 `courier-deployer`，而且步驟 1 的權限設定都成功執行過。
- **記錄顯示「登入失敗」**：檢查 Secret Manager 裡的帳號密碼，前後不能有多餘的空白或換行。
- **記錄顯示找不到「呼叫快遞」、「小件」或「呼叫」**：網站的畫面可能和預期不同，需要依實際畫面調整 `do_task()`。
- **費用**：Cloud Build（每月 2500 分鐘）、Cloud Run、Cloud Scheduler（3 個排程以內）、Secret Manager 都在免費額度內。映像檔存在 Artifact Registry 大約 2 GB，超過免費的 0.5 GB，每月約 US$0.15。舊的映像可以定期到 Artifact Registry 刪除。
