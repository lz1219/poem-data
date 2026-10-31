# 江山行止 · 文献后端（Django）

Django + DRF：`/admin` 录入，`/api/*` 只读，`/` 托管静态前端。
接口路径与 FastAPI 版一致，前端无需改动。

## 为什么是 Django

FastAPI 没有内建的用户、角色、权限、后台。要做「多人录入 + 权限 + 审计」，
Python 生态里的对等物是 Django：

| 需求 | Django 内建 |
|---|---|
| 登录 / 用户 / 组 | ✅ |
| 对象级权限 | ✅ |
| 管理后台（增删改查） | ✅ |
| 操作日志 | ✅（admin 自带 History） |
| 迁移与模型 | ✅ |

## 本地启动

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

$env:DATA_DIR='..\data'
$env:PUBLIC_DIR='..'
$env:PGHOST='47.94.110.181'; $env:PGPORT='5432'
$env:PGUSER='lz9527'; $env:PGPASSWORD='<password>'; $env:PGDATABASE='jiangshan'

.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py import_json          # data/*.json → 数据库
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver 127.0.0.1:5322
```

- 前台：<http://127.0.0.1:5322/>
- 后台：<http://127.0.0.1:5322/admin/>
- 接口：<http://127.0.0.1:5322/api/health>

## 数据流向

```
data/*.json  ──import_json──▶  数据库（编辑态）
                                     │ admin 修改
                                     ▼
                              导出（待做）──▶ data/*.json ──git──▶ 发布
```

**规矩**：一次只有一个真相。导入是单向的（JSON → DB）；
若要在后台改，就必须配套「导出回 JSON」这一步，否则 git 里的版本会落后。

## 模型

| 模型 | 说明 |
|---|---|
| `Edition` | 版本（可成谱系） |
| `Person` | 人物（生卒、字号、别名、CBDB） |
| `Work` | 作品（繁简正文、大意、注释、赏析、出处） |
| `Apparatus` | 校记（底本/异文/判定/依据，依据必填） |
| `Commentary` | 历代评点（评者·朝代·原文·出处，缺一不可） |
| `Dating` | 系年考辨（多说法并列） |
| `Journey` / `Stop` / `JourneyLink` | 行迹 / 站点 / 承接语 |

模型层内置校验：校记无依据、评点缺要素、站点无出处，**保存即报错**。

## 接口

```
GET /api/health   /api/meta   /api/index
GET /api/works    ?genre=&level=&author=&q=&limit=&offset=
GET /api/works/<key>
GET /api/persons  /api/persons/<key>
GET /api/journeys /api/journeys/<key>
GET /api/comments/<workKey>
GET /api/search?q=&scope=works|corpus|all
```

`scope=corpus` 直连 PostgreSQL 检索 66,968 首诗，带 60 秒内存缓存。
