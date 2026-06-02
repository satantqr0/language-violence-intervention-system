# 语言暴力干预系统

基于端侧语音识别与混合语义分析的语言暴力检测及主动干预系统

## 项目概述

本项目实现了一套可在 Raspberry Pi 5 上持续运行的语言暴力检测与主动干预样机，提供本地检测服务和受保护的 Web 管理控制台。

## 开发背景

很多伤害并不一定来自一次剧烈冲突，而是来自长期反复出现的否定、羞辱、威胁、讽刺、冷暴力和失控表达。家庭关系具有高频、长期、强情感连接的特点，一个人在家庭中的安全感、自我评价、压力水平和情绪调节能力，往往会受到日常互动方式的持续影响。世界卫生组织也将亲友关系列为影响健康的重要因素之一，并指出亲密关系暴力、儿童虐待和家庭暴力暴露会增加身心健康风险。

现实中，语言暴力又常常具有隐蔽性：它不像肢体伤害那样容易留下直接证据，也可能被当事人习惯性地解释为“脾气不好”“家里小事”“只是说话难听”。但持续的攻击性表达会逐渐改变家庭成员之间的沟通模式，让受害者长期处于紧张、防御和自我怀疑之中，也会让儿童和青少年在重要成长阶段接触到不健康的冲突处理方式。

本项目的开发初衷，是把家庭中的高风险语言互动尽早“看见、记录、提醒、打断”。系统不试图替代心理咨询、医学诊断、法律判断或紧急救援，而是作为一种端侧辅助工具，帮助家庭成员、照护者或研究者在保护隐私的前提下，识别反复出现的攻击性沟通、观察趋势变化，并在风险升高时提供及时提醒和人工复核入口。

## 作用与效果简介

语言暴力干预系统面向家庭、伴侣沟通、教育陪伴和儿童保护等场景，通过麦克风采集环境语音，在本地完成语音分段、转写、声学风险分析和语义风险检测；当系统判断出现高风险表达或异常声学信号时，可以播放温和的语音干预提示，并把事件记录到受保护的本地日志中。

系统希望达到的效果包括：

- **提前发现风险**：对辱骂、威胁、贬低、情绪操控、冷暴力等表达进行持续观察，减少“事后才意识到问题长期存在”的情况。
- **即时打断升级**：在冲突升高时播放非攻击性的提醒话术，帮助现场从自动化争吵节奏中短暂停下来。
- **支持复盘改进**：通过事件列表、趋势报告和人工标注，帮助使用者了解高风险互动出现的时间、频率、场景和变化趋势。
- **保护家庭成员隐私**：默认不保存原始录音，声纹模板、画像、心理筛查和安全处置记录均本地保存，并与内容观察分离。
- **降低误识别和资源浪费**：提供电视/歌曲声音过滤、VAD 人声检测和中文本地化展示，减少观看电视、播放歌曲或噪声造成的误触发。
- **保留人工判断空间**：所有检测结果都只是辅助信号，涉及安全风险、心理状态或人员身份时，必须由人工复核，必要时寻求专业支持。

### 核心能力

- 🎤 **端侧 ASR**: 本地 Whisper base 模型离线转写，无需云端
- 😊 **情绪分析**: 实时语调情绪量化，高风险预警
- 🧠 **双引擎检测**: 规则引擎(快速预检) + LLM(深度语义)
- 🎯 **场景自适应**: 家庭/夫妻/教育/儿童保护/自定义
- 👤 **声纹识别**: 实验性本地特征比对；生产级身份识别仍需接入并校验正式声纹方案
- 📢 **主动干预**: 本地 Edge TTS 即时语音干预
- 📝 **完整日志**: JSONL + CSV 双格式本地存储

## 硬件要求

### 推荐配置

| 设备 | 配置 | 状态 |
|------|------|------|
| 树莓派 5 | 8GB RAM | ✅ 完美支持 |
| Mac Mini M1/M2 | 8GB+ RAM | ✅ 完美支持 |
| 通用 x86_64 PC | 8GB+ RAM | ✅ 支持 |

### 采音设备

- **USB 麦克风阵列**: ReSpeaker 4-Mic (推荐)
- **USB 单麦**: 任意 16kHz 采样率麦克风
- **3.5mm 麦克风**: 需外接声卡

### 发声单元

发声单元用于播放系统生成的干预提示音，是“主动干预”链路的关键硬件。没有扬声器时，系统仍可完成检测、记录和 Web 告警，但无法在现场即时播放语音提醒。

推荐配置：

| 发声单元 | 说明 | 适用情况 |
|----------|------|----------|
| USB 小音箱 | 推荐方案，树莓派可直接识别为 USB Audio 设备 | 独立部署、桌面/客厅场景 |
| USB 声卡 + 有源音箱 | 适合需要更大音量或更稳定输出的场景 | 房间较大、需要外接功放 |
| HDMI 显示器/电视扬声器 | 通过 HDMI 输出声音 | 设备连接显示器或电视时 |
| 蓝牙音箱 | 可用但不推荐作为首选 | 对延迟和断连不敏感的测试场景 |

树莓派 5 没有原生 3.5mm 模拟音频口；如果需要接传统有源音箱，建议使用 USB 声卡、USB 音箱或带音频输出的扩展板。麦克风阵列本身即使暴露播放设备，也不建议作为主要发声单元，因为音量、音质和回声控制通常不如独立音箱。

部署建议：

- 将发声单元与麦克风保持一定距离，避免正对麦克风，减少回声和啸叫。
- 音量以“现场能听清提醒、但不会压过正常谈话”为宜。
- 如果启用电视/歌曲声音过滤，应在发声单元和麦克风位置固定后再做校准。
- 儿童保护或夜间场景可使用较柔和音量，避免提示音本身造成惊吓。

系统会自动选择可用播放设备，也可通过 `.env` 指定输出设备：

```bash
# 查看 ALSA 播放设备
aplay -l

# 示例：指定 USB 音箱或 USB 声卡
VD_AUDIO_OUTPUT_DEVICE=plughw:CARD=Device,DEV=0
```

播放链路优先级为：显式配置的 `VD_AUDIO_OUTPUT_DEVICE`、系统可用的 PulseAudio/PipeWire 输出、USB/非 HDMI ALSA 播放设备、系统默认播放设备。可使用 `scripts/audio_diagnose.sh` 检查音箱识别、音量、播放后端和测试音输出。

## 快速安装

### 1. 系统依赖 (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y python3-pip portaudio19-dev libasound2-dev mpg123 mpv
```

### 2. 克隆项目

```bash
cd ~/projects
git clone <repo_url> language-violence-intervention-system
cd language-violence-intervention-system
```

### 3. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置

密钥只放入 `.env`，不要写入 `config/config.json`：

```bash
cp .env.example .env
DASHSCOPE_API_KEY=
VD_WEB_USERNAME=console
VD_WEB_PASSWORD=请设置强密码
```

### 6. 运行

```bash
python3 src/main.py
```

## 树莓派 5 部署

当前部署目标默认配置为：

```bash
PI_HOST=192.168.1.100
PI_USER=pi
REMOTE_DIR=/home/pi/language-violence-intervention-system
```

### 一键同步并安装

建议安装 SSH key 后部署：

```bash
export SSH_KEY="$HOME/.ssh/language_violence_pi_example"
export SUDO_PASSWORD='你的sudo密码'
bash scripts/deploy_pi.sh
```

初次安装公钥之前也可临时使用 `SSHPASS` 环境变量；任何密码都不要写入脚本。
在本机钥匙串存在 `language-violence-pi-sudo` 项时，也可直接运行 `bash scripts/deploy.sh`。

部署脚本会完成：

- 同步项目到树莓派 `/home/pi/language-violence-intervention-system`
- 执行 `scripts/setup.sh` 安装系统依赖和 Python 依赖
- 生成 `.env` 环境变量文件模板
- 安装并启用 systemd 服务：
  - `language-violence-intervention-system.service`
  - `language-violence-web.service`
  - `language-violence-audio-upload.timer` 可选

### 树莓派上常用命令

```bash
sudo systemctl status language-violence-intervention-system.service
sudo systemctl status language-violence-web.service
sudo journalctl -u language-violence-intervention-system.service -f
sudo journalctl -u language-violence-web.service -f
```

Web 管理页面：

```text
https://192.168.1.100:5000
```

首次打开时浏览器会提示本地自签名证书，确认树莓派地址后即可继续；认证口令通过 `.env` 配置。

### 环境变量

部署后编辑树莓派上的 `.env`：

```bash
nano /home/pi/language-violence-intervention-system/.env
```

常用配置：

```bash
DASHSCOPE_API_KEY=
VD_WEB_USERNAME=pi
VD_WEB_PASSWORD=请设置独立强密码
VD_AUDIO_DIR=/home/pi/language-violence-intervention-system/audio
VD_DATA_DIR=/home/pi/language-violence-intervention-system/data
VD_AUDIO_OUTPUT_DEVICE=plughw:CARD=Device,DEV=0
SMB_USER=
SMB_PASS=
SMB_SHARE=
```

不要把 `.env`、录音、日志提交或同步给无关人员。

## 使用说明

### 首次使用

1. **人员画像与本人筛查**:
   - 「人员画像」按已转写的说话内容形成互动安全、情绪张力、痛苦/求助、生命安全相关表达和支持性沟通观察，并保留对应文字证据。
   - 内容观察不读取声纹模板，也不能替代心理评估或医疗诊断。
   - 画像中提供 `PHQ-9` 与 `GAD-7` 本人自愿自报筛查；仅保存可随时删除的总分和提示结果，不保存逐题答案。国家卫生健康委《消防救援人员职业健康保护指南》（`GBZ/T 343-2026`，`2026-07-01` 实施）附录 G 列示这两项自陈量表；本系统仅将其作为量表出处参考，不能作为家庭个案诊断依据。
   - 高严重度互动风险、生命安全相关表达，以及本人筛查产生的紧急安全提示，会进入独立的「安全处置」列表；应由人工记录核实状态、采取措施和后续安排。

2. **注册声纹**（可选，须征得本人同意）:
   - 在 Web 控制台打开独立的「声纹管理」，选择已保存的具名档案。
   - 勾选知情同意后点击「采集样本」；建议安静环境中采集 2 至 3 次。
   - 声纹由本机 ECAPA-TDNN 模型提取 embedding 并保存在 `data/voiceprints.json`，采集原音频不会保存，也不会上传云端。
   - 声纹识别是概率匹配，页面提供「测试识别」和「删除模板」；声纹身份管理与内容画像互相分离。

3. **校准电视与歌曲声音过滤**:
   - 当前 ReSpeaker 音频输入为单声道，不能可靠依据声源方向区分电视对白与房间人声；控制台提供本机声学特征校准过滤。
   - 在「运行模式」的「媒体声过滤」中，分别采集实际电视/歌曲播放样本和经本人同意的真人说话样本；系统只保存声学特征模板，不保存校准原音频。
   - 高置信匹配到媒体样本的声音会在 ASR 和云端分析前跳过；不确定声音和异常大音量声音继续进入检测，以降低重要风险漏检概率。
   - 启用媒体过滤后，DashScope ASR 会在本地完成分段与过滤后上传，而不是边收音边上传。

4. **选择场景**:
   系统启动后自动进入默认场景(家庭)，可通过配置或语音切换。

5. **开始检测**:
   系统自动检测环境中的语音，检测到暴力时自动干预。

### 场景说明

| 场景 | 灵敏度 | 适用场景 |
|------|--------|----------|
| 家庭 | 0.6 | 普通家庭成员间 |
| 夫妻 | 0.7 | 夫妻关系 |
| 教育 | 0.5 | 师生教育场景 |
| 儿童保护 | 0.9 | 含儿童的高灵敏度模式 |
| 自定义 | 0.6 | 用户自定义规则 |

### 干预话术

- **高严重度**: "请冷静一下，换一种表达方式可能会有更好的效果。"
- **中严重度**: "也许我们可以换个角度看这个问题。"
- **低严重度**: "希望你们能相互理解，好好沟通。"

## 项目结构

```
language-violence-intervention-system/
├── src/
│   ├── main.py              # 主程序入口
│   ├── audio_capture.py     # 音频采集模块
│   ├── vad_engine.py        # VAD 人声检测
│   ├── asr_engine.py        # Whisper ASR
│   ├── emotion_analyzer.py  # 情绪分析
│   ├── semantic_analyzer.py # 混合语义分析
│   ├── scene_manager.py     # 场景管理
│   ├── speaker_profile_engine.py # 内容观察画像
│   ├── mental_screening_engine.py # 本人自愿心理筛查
│   ├── voiceprint.py        # 声纹识别
│   ├── tts_engine.py        # TTS 干预
│   └── event_logger.py      # 日志记录
├── config/
│   ├── config.json          # 主配置
│   └── violence_rules.json  # 暴力检测规则
├── logs/                     # 日志输出
├── models/                   # 模型存储
├── scripts/
│   ├── setup.sh            # 安装脚本
│   └── install_whisper.sh   # Whisper 下载
└── requirements.txt
```

## 性能指标

| 指标 | 数值 |
|------|------|
| 项目 | 状态 |
|------|------|
| 树莓派音频采集与 Whisper 链路 | 已完成实机联调 |
| 自动化回归测试 | 以 `python3 tests/run_all.py` 结果为准 |
| 误报/漏报与干预有效性 | 需使用经同意的真实样本验收 |
| 声纹身份准确率 | 尚未形成生产验收结论 |

## 隐私保护

- ✅ 音频数据不持久化
- ✅ 默认不开启录音留存
- ✅ 不配置云服务密钥时使用本地 Whisper 检测链路
- ⚠ 启用 DashScope ASR/LLM/TTS 时，相应文本或音频会发送给配置的云服务
- ✅ 日志文件本地存储
- ✅ 事件日志、人工反馈、声纹模板、心理筛查和安全处置记录仅允许设备用户读取（`0600`）
- ⚠ Web 控制台当前使用自签名 TLS 证书，正式持续使用前建议配置受信任的本地证书或反向代理

## 故障排除

### 麦克风与发声单元问题

```bash
# 列出可用音频设备
python3 -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)[\"name\"]}') for i in range(p.get_device_count())]"

# 列出可用播放设备
aplay -l
```

### Whisper 模型下载失败

```bash
# 手动下载
python3 -c "import whisper; whisper.download_model('base')"
```

### TTS 无声音

```bash
# 检查播放器
which mpv
which aplay

# 生成测试音并播放
python3 - <<'PY'
import math, struct, wave
with wave.open('/tmp/test_tone.wav', 'w') as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(8000)
    for i in range(8000):
        f.writeframes(struct.pack('<h', int(12000 * math.sin(2 * math.pi * 440 * i / 8000))))
PY
aplay /tmp/test_tone.wav
```

## 许可证

Apache License 2.0。请保留 `LICENSE` 与 `NOTICE` 文件中的版权、署名、专利提示和免责声明。

另见 `LEGAL_NOTICE.md`：本项目不是医疗诊断、法律证据或紧急救援替代系统；涉及人员识别、画像和筛查时必须取得合法依据与必要同意。

## 参考

- [OpenAI Whisper](https://github.com/openai/whisper)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Edge TTS](https://github.com/rany2/edge-tts)
