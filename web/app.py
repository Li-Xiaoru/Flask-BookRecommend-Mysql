from utils import load_config
from logger import setup_log
from flask import Flask, request, render_template, session, redirect, url_for
from utils import mysql
import math

# 加载配置
config = load_config()
logger = setup_log(__name__)
app = Flask(__name__)
# 从配置文件读取SECRET_KEY，避免硬编码
app.config['SECRET_KEY'] = config.get('secret_key', 'default_secure_key_123456')
# 初始化mysql连接
mysql = mysql(config['mysql'])


@app.route("/")
def root():
    """
    主页
    :return: home.html
    """
    login, userid = False, ''
    if 'userid' in session:
        login, userid = True, session['userid']

    # 热门书籍（修复SQL注入：参数化查询）
    hot_books = []
    # 安全的参数化SQL：IN查询拼接占位符 + 参数传入
    book_ids = config.get('bookid', [])
    if book_ids:
        # 生成对应数量的占位符 (%s)
        placeholders = ', '.join(['%s'] * len(book_ids))
        sql = f"SELECT BookTitle, BookAuthor, BookID, ImageM FROM Books WHERE BookID IN ({placeholders})"
        try:
            # 参数化执行，避免字符串拼接
            hot_books = mysql.fetchall_db(sql, tuple(book_ids))
            hot_books = [[v for k, v in row.items()] for row in hot_books]
        except Exception as e:
            logger.exception("select hot books error: {}".format(e))

    return render_template('Index.html',
                           login=login,
                           books=hot_books,
                           useid=userid,
                           name="index")


@app.route("/guess")
def guess():
    """
    猜你喜欢
    :return: Index.html
    """
    login, userid, error = False, '', False
    if 'userid' in session:
        login, userid = True, session['userid']

    guess_books = []
    if login:
        # 修复SQL注入：参数化查询（所有变量用%s占位）
        sql = """
              SELECT e.BookTitle, e.BookAuthor, e.BookID, e.ImageM
              FROM Books e
                       INNER JOIN (SELECT c.BookID, SUM(c.Rating) as score \
                                   FROM (SELECT UserID, BookID, Rating \
                                         FROM Bookrating \
                                         WHERE Rating != 0 LIMIT %s) c \
                                            INNER JOIN (SELECT UserID \
                                                        FROM (SELECT UserID, BookID \
                                                              FROM Bookrating \
                                                              WHERE Rating != 0 LIMIT %s) a \
                                                                 INNER JOIN (SELECT BookID \
                                                                             FROM Booktuijian \
                                                                             WHERE UserID = %s) b \
                                                                            ON a.BookID = b.BookID) d \
                                                       ON c.UserID = d.UserID \
                                   GROUP BY c.BookID \
                                   ORDER BY score DESC LIMIT 10) f ON e.BookID = f.BookID \
              """
        try:
            # 传入参数元组，避免字符串格式化注入
            limit = config.get('limit', 100)
            params = (limit, limit, userid)
            guess_books = mysql.fetchall_db(sql, params)
            guess_books = [[v for k, v in row.items()] for row in guess_books]
        except Exception as e:
            logger.exception("select guess books error: {}".format(e))

    return render_template('Index.html',
                           login=login,
                           books=guess_books,
                           useid=userid,
                           name="guess")


@app.route("/recommend")
def recommend():
    """
    推荐页面
    :return: Index.html
    """
    login, userid, error = False, '', False
    if 'userid' in session:
        login, userid = True, session['userid']

    recommend_books = []
    if login:
        # 修复SQL注入：参数化查询
        sql = """
              SELECT BookTitle, BookAuthor, a.BookID, a.ImageM, score
              FROM Books a
                       LEFT JOIN Booktuijian as b ON a.BookID = b.BookID
              WHERE b.UserID = %s
              ORDER BY score DESC \
              """
        try:
            recommend_books = mysql.fetchall_db(sql, (userid,))
            recommend_books = [[v for k, v in row.items()] for row in recommend_books]
        except Exception as e:
            logger.exception("select recommend books error: {}".format(e))

    return render_template('Index.html',
                           login=login,
                           books=recommend_books,
                           useid=userid,
                           name="recommend")


@app.route("/loginForm")
def loginForm():
    """
    跳转登录页
    :return: Login.html
    """
    if 'userid' in session:
        return redirect(url_for('root'))
    else:
        return render_template('Login.html', error='')


@app.route("/registerationForm")
def registrationForm():
    """
    跳转注册页
    :return: Register.html
    """
    return render_template("Register.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    注册（修复SQL注入）
    :return: Register.html/Login.html
    """
    try:
        if request.method == 'POST':
            # 参数校验
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            age = request.form.get('age', '').strip()

            if not all([username, password, age]):
                return render_template('Register.html', error='请填写完整信息')

            # 修复SQL注入：参数化插入
            sql = "INSERT INTO User (UserID, Location, Age) VALUES (%s, %s, %s)"
            try:
                mysql.exe(sql, (username, password, age))
                logger.info(f"username:{username} register success")
                return render_template('Login.html')
            except Exception as e:
                mysql.rollback()
                logger.exception(f"username:{username} register failed: {e}")
                return render_template('Register.html', error='注册失败：用户名已存在或格式错误')
    except Exception as e:
        logger.exception(f"register function error: {e}")
        return render_template('Register.html', error='注册出错')


def is_valid(username, password):
    """
    登录验证（修复SQL注入）
    :param username: 用户名
    :param password: 密码
    :return: True/False
    """
    if not all([username, password]):
        return False

    try:
        # 修复SQL注入：参数化查询
        sql = "SELECT UserID, Location as Username FROM User WHERE UserID = %s AND Location = %s"
        result = mysql.fetchone_db(sql, (username, password))

        if result:
            logger.info(f'username:{username} login success')
            return True
        else:
            logger.info(f'username:{username} login failed: 账号密码错误')
            return False
    except Exception as e:
        logger.exception(f'username:{username} login error: {e}')
        return False


@app.route("/login", methods=['POST', 'GET'])
def login():
    """
    登录页提交
    :return: Login.html/Admin.html/root
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # 管理员登录（建议移到配置文件）
        if username == 'admin' and password == 'admin':
            session['userid'] = username
            return render_template('Admin.html', userid='admin')

        # 普通用户登录验证
        if is_valid(username, password):
            session['userid'] = username
            return redirect(url_for('root'))
        else:
            error = '账号密码输入错误'
            return render_template('Login.html', error=error)

    # GET请求跳转登录页
    return redirect(url_for('loginForm'))


@app.route("/logout")
def logout():
    """
    退出登录
    :return: root
    """
    session.pop('userid', None)
    return redirect(url_for('root'))


def update_recommend_book(UserID, BookID):
    """
    更新推荐数据（修复SQL注入）
    """
    if not all([UserID, BookID]):
        logger.warning("update_recommend_book: UserID/BookID为空")
        return

    # 1. 查询当前score（参数化）
    sql_select = "SELECT score FROM Booktuijian WHERE UserID = %s AND BookID = %s"
    score = mysql.fetchone_db(sql_select, (UserID, BookID))

    if score:
        # 更新score
        score_val = int(score['score'])
        score_val = 10 if score_val + 0.5 > 10 else score_val + 0.5
        sql_update = "UPDATE Booktuijian SET score = %s WHERE UserID = %s AND BookID = %s"
        try:
            mysql.exe(sql_update, (int(score_val), UserID, BookID))
            logger.info(f"update_recommend_book: {sql_update} | params: {int(score_val)}, {UserID}, {BookID}")
        except Exception as e:
            mysql.rollback()
            logger.exception(f"update_recommend_book update error: {e}")
    else:
        # 插入新记录
        score_val = 0.5
        sql_insert = "INSERT INTO Booktuijian (UserID, BookID, score) VALUES (%s, %s, %s)"
        try:
            mysql.exe(sql_insert, (UserID, BookID, float(score_val)))
            logger.info(f"update_recommend_book: {sql_insert} | params: {UserID}, {BookID}, {score_val}")
        except Exception as e:
            mysql.rollback()
            logger.exception(f"update_recommend_book insert error: {e}")


@app.route("/bookinfo", methods=['POST', 'GET'])
def bookinfo():
    """
    书籍详情（修复SQL注入）
    :return: BookInfo.html
    """
    score = 0
    userid = session.get('userid')
    login = bool(userid)

    try:
        if request.method == 'GET':
            # 获取并校验bookid参数
            bookid = request.args.get('bookid', '').strip()
            if not bookid:
                logger.warning("bookinfo: bookid参数为空")
                return render_template('BookInfo.html', book_info=[], login=login, useid=userid, score=score)

            # 查询书籍信息（参数化）
            sql_book = "SELECT BookTitle, BookID, PubilcationYear, BookAuthor, ImageM FROM Books WHERE BookID = %s"
            book_info = mysql.fetchall_db(sql_book, (bookid,))

            if book_info:
                book_info = [v for k, v in book_info[0].items()]
                # 更新推荐数据（仅登录用户）
                if userid:
                    update_recommend_book(userid, bookid)

                    # 查询用户评分（参数化）
                    sql_rating = "SELECT Rating FROM Bookrating WHERE UserID = %s AND BookID = %s"
                    rating = mysql.fetchone_db(sql_rating, (userid, bookid))
                    if rating:
                        score = int(rating['Rating'])
                        score = math.ceil(score / 2)
                        score = 10 if score > 10 else score
            else:
                book_info = []
    except Exception as e:
        logger.exception("select book info error: {}".format(e))
        book_info = []

    return render_template('BookInfo.html',
                           book_info=book_info,
                           login=login,
                           useid=userid,
                           score=score)


@app.route("/user", methods=['POST', 'GET'])
def user():
    """
    个人信息（后续补充参数化查询，当前保留结构）
    :return: UserInfo.html
    """
    login, userid = False, None
    if 'userid' not in session:
        return redirect(url_for('loginForm'))
    else:
        login, userid = True, session['userid']

    userinfo = []
    try:
        # 后续补充：个人信息查询的参数化SQL
        pass
    except Exception as e:
        logger.exception("get user info error: {}".format(e))

    return render_template('UserInfo.html',
                           login=login,
                           useid=userid,
                           userinfo=userinfo)


# 启动应用（建议移到main函数）
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)  # 生产环境关闭debug
