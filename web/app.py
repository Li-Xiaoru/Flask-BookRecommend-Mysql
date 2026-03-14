# 导入依赖库
from utils import load_config
from logger import setup_log
from flask import Flask, request, render_template, session, redirect, url_for
from utils import mysql
import math

# 初始化配置
config = load_config()
logger = setup_log(__name__)

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = config.get('secret_key', 'default_secure_key_123456')

# 初始化MySQL连接
mysql = mysql(config['mysql'])


# =============================
# 评分接口
# =============================
@app.route('/rating', methods=['POST'])
def rating():
    """
    书籍评分接口
    POST参数: book_id, rank(1-5星)
    返回: ok/error/not login
    """
    # 验证登录状态
    if 'userid' not in session:
        return "not login"

    try:
        user = session['userid']
        book_id = request.form.get('book_id')
        # 转换为10分制（5星*2）
        rank = int(request.form.get('rank', 0)) * 2

        # 参数校验
        if not book_id or rank < 0 or rank > 10:
            logger.warning(f"user:{user} rating param error - book_id:{book_id}, rank:{rank}")
            return "error"

        # 检查是否已评分
        sql_check = """
        SELECT Rating FROM Bookrating
        WHERE UserID=%s AND BookID=%s
        """
        result = mysql.fetchone_db(sql_check, (user, book_id))

        if result:
            # 更新评分
            sql_update = """
            UPDATE Bookrating
            SET Rating=%s
            WHERE UserID=%s AND BookID=%s
            """
            mysql.exe(sql_update, (rank, user, book_id))
        else:
            # 新增评分
            sql_insert = """
            INSERT INTO Bookrating(UserID, BookID, Rating)
            VALUES(%s, %s, %s)
            """
            mysql.exe(sql_insert, (user, book_id, rank))

        logger.info(f"user:{user} rate book:{book_id} score:{rank}")
        return "ok"

    except ValueError:
        # 处理rank非数字的情况
        logger.error(f"user:{session.get('userid')} rating rank is not number")
        return "error"
    except Exception as e:
        mysql.rollback()
        logger.exception(f"rating error: {str(e)}")
        return "error"


# =============================
# 首页
# =============================
@app.route("/")
def root():
    """
    首页展示热门书籍
    """
    login = False
    userid = ''

    # 检查登录状态
    if 'userid' in session:
        login = True
        userid = session['userid']

    hot_books = []
    book_ids = config.get('bookid', [])

    if book_ids and isinstance(book_ids, list):
        # 构建参数化SQL，避免注入
        placeholders = ', '.join(['%s'] * len(book_ids))
        sql = f"""
        SELECT BookTitle, BookAuthor, BookID, ImageM
        FROM Books
        WHERE BookID IN ({placeholders})
        """

        try:
            hot_books = mysql.fetchall_db(sql, tuple(book_ids))
            # 转换为列表格式
            hot_books = [[v for k, v in row.items()] for row in hot_books]
        except Exception as e:
            logger.exception(f"get hot books error: {str(e)}")

    return render_template(
        "Index.html",
        login=login,
        books=hot_books,
        useid=userid,
        name="index"
    )


# =============================
# 历史评分
# =============================


@app.route("/historical")
def historical():

    # 未登录跳转登录页
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']

    sql = """
    SELECT 
        b.BookTitle,
        b.BookAuthor,
        b.BookID,
        r.Rating
    FROM Bookrating r
    LEFT JOIN Books b
        ON r.BookID = b.BookID
    WHERE r.UserID = %s
    """

    books = []

    try:

        data = mysql.fetchall_db(sql, (userid,))

        # 转换为列表
        books = [[v for k, v in row.items()] for row in data]

    except Exception as e:

        logger.exception("historical error {}".format(e))

    return render_template(
        "Historicalscore.html",
        login=True,
        useid=userid,
        books=books
    )
# =============================
# 登录页
# =============================
@app.route("/loginForm")
def loginForm():
    """
    登录页面（已登录则跳首页）
    """
    if 'userid' in session:
        return redirect(url_for('root'))
    return render_template("Login.html", error='')


# =============================
# 注册页
# =============================
@app.route("/registerationForm")
def registrationForm():
    """
    注册页面
    """
    return render_template("Register.html")


# =============================
# 注册接口
# =============================
@app.route("/register", methods=["POST"])
def register():
    """
    用户注册接口
    POST参数: username, password, age
    """
    try:
        # 获取并清洗参数
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        age = request.form.get('age', '').strip()

        # 参数完整性校验
        if not all([username, password, age]):
            logger.warning(f"register param incomplete - username:{username}")
            return render_template("Register.html", error="信息不完整")

        # 验证年龄是否为数字
        if not age.isdigit():
            return render_template("Register.html", error="年龄必须为数字")

        # 插入用户数据
        sql = """
        INSERT INTO User(UserID, Location, Age)
        VALUES(%s, %s, %s)
        """
        mysql.exe(sql, (username, password, age))
        logger.info(f"user:{username} register success")

        # 注册成功跳登录页
        return render_template("Login.html")

    except Exception as e:
        mysql.rollback()
        logger.exception(f"register error: {str(e)}")
        return render_template("Register.html", error="注册失败")


# =============================
# 登录验证工具函数
# =============================
def is_valid(username, password):
    """
    验证用户名密码是否正确
    """
    if not (username and password):
        return False

    sql = """
    SELECT UserID
    FROM User
    WHERE UserID=%s AND Location=%s
    """
    result = mysql.fetchone_db(sql, (username, password))
    return bool(result)


# =============================
# 登录接口
# =============================
@app.route("/login", methods=["POST"])
def login():
    """
    用户登录接口
    POST参数: username, password
    """
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    # 管理员登录
    if username == "admin" and password == "admin":
        session['userid'] = username
        return render_template("Admin.html", userid="admin")

    # 普通用户登录验证
    if is_valid(username, password):
        session['userid'] = username
        return redirect(url_for("root"))

    # 登录失败
    logger.warning(f"user:{username} login failed - password error")
    return render_template("Login.html", error="账号密码错误")


# =============================
# 退出登录
# =============================
@app.route("/logout")
def logout():
    """
    退出登录，清除session
    """
    session.pop('userid', None)
    return redirect(url_for("root"))


# =============================
# 书籍详情页
# =============================
@app.route("/bookinfo")
def bookinfo():
    """
    书籍详情页面
    GET参数: bookid
    """
    score = 0
    userid = session.get('userid')
    login = bool(userid)
    book_info = []

    bookid = request.args.get("bookid")
    if not bookid:
        logger.warning("bookinfo - bookid is empty")
        return render_template("BookInfo.html", book_info=[], login=login, useid=userid, score=0)

    # 查询书籍详情
    sql = """
    SELECT BookTitle, BookID, PubilcationYear, BookAuthor, ImageM
    FROM Books
    WHERE BookID=%s
    """

    try:
        book_data = mysql.fetchone_db(sql, (bookid,))
        if book_data:
            book_info = list(book_data.values())

        # 查询用户对该书的评分
        if userid:
            sql_rating = """
            SELECT Rating
            FROM Bookrating
            WHERE UserID=%s AND BookID=%s
            """
            rating = mysql.fetchone_db(sql_rating, (userid, bookid))
            if rating:
                # 转换为5星制（10分/2，向上取整）
                score = math.ceil(int(rating['Rating']) / 2)

    except Exception as e:
        logger.exception(f"get bookinfo error: {str(e)}")

    return render_template(
        "BookInfo.html",
        book_info=book_info,
        login=login,
        useid=userid,
        score=score
    )


# =============================
# 个人中心
# =============================
@app.route("/user")
def user():
    """
    个人中心页面（需登录）
    """
    if 'userid' not in session:
        return redirect(url_for("loginForm"))

    userid = session['userid']
    return render_template(
        "UserInfo.html",
        login=True,
        useid=userid,
        userinfo=[]
    )


# =============================
# 应用启动入口
# =============================
if __name__ == '__main__':
    # 生产环境建议关闭debug
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False,
        threaded=True  # 开启多线程处理请求
    )
