# MySQL 安装指南（本机环境已实测，2026-10-11）

> 目标：第6周周六 3–4 小时内搞定"能连上、能建库、能入库 3000 条"。
> 本文档基于**本机实测环境**写的，不是通用教程——按顺序照做即可。

## 零、本机环境体检结果（省得你再查）

| 检查项 | 结果 | 结论 |
|---|---|---|
| 是否管理员 | **否**（当前进程未提权） | MYSQL MSI 需要提权 → 走免安装版最稳 |
| MySQL 是否已安装 | 未安装；但 `C:\Program Files (x86)\MySQL\MySQL Installer for Windows` **已存在** | 能提权的话可直接用这个 GUI 装 |
| 3306 端口 | **空闲** | 不用改端口 |
| 磁盘 | C: 45.3G 可用 / D: 35.5G 可用 | 建议装到 **D 盘** |
| `cryptography` 包 | **已装** | pymysql 连 MySQL 8 不会报 `cryptography is required` |
| Docker | CLI 已装，**守护进程未运行** | 要用需先启动 Docker Desktop（拉镜像约 600MB） |
| SQLite | 3.45.3（≥3.25，支持窗口函数） | 兜底方案可用 |

**推荐顺序：路线 A（免安装版，不需要管理员）→ 路线 C（已有 Installer，能提权时）→ 路线 B（Docker）→ 路线 D（SQLite 兜底）**

---

## 路线 A（推荐）：MySQL 8 免安装 ZIP 版，不需要管理员

### A1. 下载
官网 → MySQL Community Server → **ZIP Archive**（选 `mysql-8.0.xx-winx64.zip`，约 200–300MB）。
> 若下载慢：可在官网找镜像站，或用你已有的安装包。**不要下 "MySQL Installer" 的 msi**。

### A2. 解压
解压到 **`D:\mysql-8.0`**（路径不要有空格和中文）。最终应存在 `D:\mysql-8.0\bin\mysqld.exe`。

### A3. 建配置文件 `D:\mysql-8.0\my.ini`
```ini
[mysqld]
basedir=D:/mysql-8.0
datadir=D:/mysql-8.0/data
port=3306
character-set-server=utf8mb4
collation-server=utf8mb4_general_ci
# 用传统认证插件，避免老客户端兼容问题（新装的项目用不到，但能省事）
default_authentication_plugin=mysql_native_password

[client]
port=3306
default-character-set=utf8mb4
```
> 路径写**正斜杠**或双反斜杠，别写 `D:\mysql-8.0`（会被当转义符）。

### A4. 初始化（**只执行一次**）
```powershell
cd D:\mysql-8.0
.\bin\mysqld --initialize-insecure --console
```
- `--initialize-insecure` = root 初始无密码（本地学习够用，别暴露到公网）
- **`data` 目录必须是空的/不存在**，否则报错；已生成过就别再跑

### A5. 启动（前台，另开一个窗口）
```powershell
cd D:\mysql-8.0
.\bin\mysqld --console
```
看到 `ready for connections` 就是成功了。
> 想让它在后台跑：`Start-Process -FilePath "D:\mysql-8.0\bin\mysqld.exe" -ArgumentList "--console" -WindowStyle Hidden`
> **没有注册成 Windows 服务**（那需要管理员），所以**每次重启电脑后要重新启动一次**。

### A6. 设密码 + 建库（再开一个窗口）
```powershell
cd D:\mysql-8.0
.\bin\mysql -u root --skip-password
```
进 MySQL 后执行：
```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '你的密码';
CREATE DATABASE bili DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_general_ci;
SHOW DATABASES;
EXIT;
```

### A7. 配置项目并验证
```powershell
cd <你的项目目录>\bilibili-knowledge-analytics
copy .env.example .env      # 然后把 DB_PASSWORD 改成上一步的密码
pip install -r requirements.txt
python src/check.py
```
期望看到：`[PASS] MySQL 连接  版本 8.0.xx`、`[PASS] 数据库 bili  已存在`。

### A8. 建表
```powershell
mysql -u root -p bili < sql\01_schema.sql
```
> 表结构 DDL 在 `docs/03_课题技术方案.md` 第二节（video / up_author / comment / danmaku），第6周周六把它落成 `sql/01_schema.sql`。

### A 路线的坑（提前知道能省 1 小时）
| 现象 | 原因 | 处理 |
|---|---|---|
| `mysqld: Can't create directory` / `data` 报错 | data 目录已存在且非空 | 删掉 data 目录重跑 `--initialize-insecure` |
| 启动即退出，日志 `another process is using port 3306` | 端口被占（本机实测空闲） | `netstat -ano \| findstr 3306` 查进程 |
| `Access denied for user 'root'` | 已经设过密码了 | 用密码登录，或按官网步骤重置 |
| Python 报 `cryptography is required for sha256_password` | 缺 cryptography | 本机已装；换机器时 `pip install cryptography` |
| 提示 `无法加载身份验证插件 caching_sha2_password` | 老客户端 | my.ini 加 `default_authentication_plugin=mysql_native_password`（A3 已含） |
| 重启电脑后连不上 | 服务没注册（免安装版特性） | 重新执行 A5 |

---

## 路线 C：用机器上已有的 MySQL Installer（需要提权）

`C:\Program Files (x86)\MySQL\MySQL Installer for Windows\MySQLInstaller.exe` 已存在。
右键 → **以管理员身份运行** → 选 `Server only`（或 Custom，只勾 MySQL Server 8.0）→
Config Type: `Development Computer`，Port `3306`，认证方式选 `Use Legacy Authentication Method`（省事）→
设 root 密码 → 完成。之后直接跳到 **A7** 验证。

> 优点：自动注册服务，不用每次手动启动。缺点：必须能提权。

---

## 路线 B：Docker（CLI 已装，需要先启动 Docker Desktop）

```powershell
# 先手动启动 Docker Desktop，等托盘图标变绿，然后：
docker run -d --name bili-mysql -p 3306:3306 `
  -e MYSQL_ROOT_PASSWORD=你的密码 `
  -e MYSQL_DATABASE=bili `
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_general_ci

docker ps                      # 确认状态 Up
```
`.env` 里 `DB_HOST=127.0.0.1`、`DB_PORT=3306` 即可。
> 注意：**在受限沙箱里 Docker 不可用**（无法打开命名管道）；要在你自己的普通终端里执行。
> 好处：环境隔离、随时 `docker rm -f bili-mysql` 重来；坏处：占内存、镜像约 600MB。

---

## 路线 D（兜底）：先用 SQLite 跑通，MySQL 补装后一条配置切换

**用途**：如果周六 MySQL 卡住了，**不要停工**——先用 SQLite 把分析跑起来，周一再补 MySQL。

项目已内置切换开关（`config.yaml`）：
```yaml
database:
  backend: sqlite            # 改成 sqlite；恢复 MySQL 就改回 mysql
  sqlite_path: data/bili.db
```
```powershell
python -m src.config         # 应显示 DB URL 以 sqlite:/// 开头
python src/check.py          # SQLite 检查会 PASS
```

**必须知道的差异（否则你后面会踩坑）**：
| 差异点 | MySQL | SQLite |
|---|---|---|
| 取小时 | `HOUR(pub_time)` | `strftime('%H', pub_time)` |
| 取日期 | `DATE(pub_time)` | `date(pub_time)` |
| `to_sql` 追加 | 依赖驱动参数 | 用 `if_exists='append'` 即可 |
| 并发/权限 | 有用户体系 | 无 |
| 中位数窗口函数 | 支持 | 支持（3.25+，本机 3.45.3） |

> 结论：**SQLite 只当"不误工的过渡"**。简历上必须写 MySQL（JD 高频要求），而且 `HOUR()` / 权限 / 索引这些在面试里会被问。
> 建议做法：分析 SQL 用 MySQL 方言写，SQLite 只用于第6–7周验证链路；一旦 MySQL 通了立刻切回。

---

## 验收清单（周六收工前逐条打勾）

- [ ] `python src/check.py` → MySQL 连接 PASS、数据库 `bili` 存在
- [ ] `sql/01_schema.sql` 建表成功（4 张表：video / up_author / comment / danmaku）
- [ ] `SELECT COUNT(*) FROM video;` ≥ 3000
- [ ] 重启电脑后知道怎么把 MySQL 再启动起来（路线 A 要手动起）
- [ ] `.env` 已加入 `.gitignore`（密码绝不进仓库）
