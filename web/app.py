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
# 首页路由（根路由）
# =============================
@app.route("/")
def root():
    """首页（猜你喜欢）"""
    login, userid, error = False, '', False
    if 'userid' in session:
        login, userid = True, session['userid']
    # 推荐书籍
    guess_books = []
    if login:
        sql = """select e.BookTitle,
                       e.BookAuthor,
                       e.BookID,
                       e.ImageM
                       from Books e
                inner join (select  c.BookID,
                                    sum(c.Rating) as score  
                            from (select UserID,BookID,Rating from Bookrating where Rating != 0
                                limit {0}) c 
                            inner join (select UserID 
                                        from (select UserID,BookID from Bookrating where Rating != 0
                                        limit {0}) a 
                                        inner join (select BookID from Booktuijian where UserID=%s) b
                                        on a.BookID=b.BookID ) d
                            on c.UserID=d.UserID
                            group by c.BookID 
                            order by score desc 
                            limit 10) f
                on e.BookID = f.BookID""".format(config['limit'])
        try:
            guess_books = mysql.fetchall_db(sql, (session['userid'],))
            guess_books = [[v for k, v in row.items()] for row in guess_books]
        except Exception as e:
            logger.exception("select guess books error: {}".format(e))
    return render_template('Index.html',
                           login=login,
                           books=guess_books,
                           useid=userid,
                           name="guess")


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
                    SELECT Rating \
                    FROM Bookrating
                    WHERE UserID = %s \
                      AND BookID = %s \
                    """
        result = mysql.fetchone_db(sql_check, (user, book_id))

        if result:
            # 更新评分
            sql_update = """
                         UPDATE Bookrating
                         SET Rating=%s
                         WHERE UserID = %s \
                           AND BookID = %s \
                         """
            mysql.exe(sql_update, (rank, user, book_id))
        else:
            # 新增评分
            sql_insert = """
                         INSERT INTO Bookrating(UserID, BookID, Rating)
                         VALUES (%s, %s, %s) \
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
# 辅助函数：更新推荐书籍评分
# =============================
def update_recommend_book(UserID, BookID):
    """更新用户-书籍的推荐分数（猜你喜欢的核心逻辑）"""
    if not (UserID and BookID):
        return

    try:
        # 检查是否已有推荐记录
        sql_check = """
                    SELECT score \
                    FROM Booktuijian
                    WHERE UserID = %s \
                      AND BookID = %s \
                    """
        score = mysql.fetchone_db(sql_check, (UserID, BookID))

        if score:
            # 已有记录：分数+0.5（上限10）
            score = float(score['score'])  # 修正：使用float避免整数截断
            new_score = 10.0 if (score + 0.5) > 10 else (score + 0.5)
            sql_update = """
                         UPDATE Booktuijian
                         SET score=%s
                         WHERE UserID = %s \
                           AND BookID = %s \
                         """
            mysql.exe(sql_update, (new_score, UserID, BookID))
            logger.info(f"update recommend score: user={UserID}, book={BookID}, new_score={new_score}")
        else:
            # 无记录：初始化分数0.5
            sql_insert = """
                         INSERT INTO Booktuijian (UserID, BookID, score)
                         VALUES (%s, %s, %s) \
                         """
            mysql.exe(sql_insert, (UserID, BookID, 0.5))
            logger.info(f"init recommend score: user={UserID}, book={BookID}, score=0.5")
    except Exception as e:
        mysql.rollback()
        logger.exception(f"update_recommend_book error: {str(e)}")


# =============================
# 猜你喜欢
# =============================
@app.route("/guess")
def guess():
    """
    猜你喜欢
    :return: Index.html
    """
    login, userid, error = False, '', False
    if 'userid' in session:
        login, userid = True, session['userid']
    # 推荐书籍
    guess_books = []
    if login:
        sql = """select e.BookTitle,
                       e.BookAuthor,
                       e.BookID,
                       e.ImageM
                       from Books e
                inner join (select  c.BookID,
                                    sum(c.Rating) as score  
                            from (select UserID,BookID,Rating from Bookrating where Rating != 0
                                limit {0}) c 
                            inner join (select UserID 
                                        from (select UserID,BookID from Bookrating where Rating != 0
                                        limit {0}) a 
                                        inner join (select BookID from Booktuijian where UserID=%s) b
                                        on a.BookID=b.BookID ) d
                            on c.UserID=d.UserID
                            group by c.BookID 
                            order by score desc 
                            limit 10) f
                on e.BookID = f.BookID""".format(config['limit'])
        try:
            guess_books = mysql.fetchall_db(sql, (session['userid'],))
            guess_books = [[v for k, v in row.items()] for row in guess_books]
        except Exception as e:
            logger.exception("select guess books error: {}".format(e))
    return render_template('Index.html',
                           login=login,
                           books=guess_books,
                           useid=userid,
                           name="guess")


# =============================
# 推荐书籍页面
# =============================
@app.route("/recommend")
def recommend():
    """推荐书籍页面：展示用户专属推荐（基于Booktuijian表）"""
    login, userid = False, ''
    recommend_books = []

    # 检查登录状态
    if 'userid' in session:
        login, userid = True, session['userid']

    # 已登录：查询推荐书籍
    if login:
        sql_recommend = """
                        SELECT BookTitle, BookAuthor, a.BookID, a.ImageM, b.score
                        FROM Books a
                                 LEFT JOIN Booktuijian b ON a.BookID = b.BookID
                        WHERE b.UserID = %s
                        ORDER BY b.score DESC \
                        """
        try:
            recommend_books = mysql.fetchall_db(sql_recommend, (userid,))
            recommend_books = [[v for k, v in row.items()] for row in recommend_books]
        except Exception as e:
            logger.exception(f"get recommend books error: {str(e)}")

    return render_template(
        "Index.html",
        login=login,
        books=recommend_books,
        useid=userid,
        name="recommend"  # 标记为推荐页面
    )


# =============================
# 历史评分
# =============================
@app.route("/historical")
def historical():
    """历史评分页面"""
    # 未登录跳转登录页
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']
    sql = """
          SELECT b.BookTitle, \
                 b.BookAuthor, \
                 b.BookID, \
                 r.Rating, \
                 b.ImageM
          FROM Bookrating r
                   LEFT JOIN Books b
                             ON r.BookID = b.BookID
          WHERE r.UserID = %s \
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
    """登录页面（已登录则跳首页）"""
    if 'userid' in session:
        return redirect(url_for('root'))
    return render_template("Login.html", error='')


# =============================
# 注册页
# =============================
@app.route("/registerationForm")
def registrationForm():
    """注册页面"""
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

        # 插入用户数据（防止SQL注入）
        sql = """
              INSERT INTO User(UserID, Location, Age)
              VALUES (%s, %s, %s) \
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
    """验证用户名密码是否正确"""
    if not (username and password):
        return False

    sql = """
          SELECT UserID
          FROM User
          WHERE UserID = %s \
            AND Location = %s \
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
    """退出登录，清除session"""
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
          WHERE BookID = %s \
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
                         WHERE UserID = %s \
                           AND BookID = %s \
                         """
            rating = mysql.fetchone_db(sql_rating, (userid, bookid))
            if rating:
                # 转换为5星制（10分/2，向上取整）
                score = math.ceil(int(rating['Rating']) / 2)
                score = min(score, 5)  # 限制最大为5星

        # 访问书籍详情时，更新推荐分数（猜你喜欢核心）
        if userid:
            update_recommend_book(userid, bookid)

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
    """个人中心页面（需登录）"""
    if 'userid' not in session:
        return redirect(url_for("loginForm"))

    userid = session['userid']
    # 查询用户信息
    userinfo = []
    try:
        sql = "SELECT UserID, Location, Age FROM User WHERE UserID=%s"
        result = mysql.fetchone_db(sql, (userid,))
        if result:
            userinfo = list(result.values())
    except Exception as e:
        logger.exception(f"get user info error: {str(e)}")

    return render_template(
        "UserInfo.html",
        login=True,
        useid=userid,
        userinfo=userinfo
    )


# =============================
# 购物车相关路由
# =============================
@app.route("/order")
def order():
    """购物车页面"""
    login, userid = False, None
    if 'userid' not in session:
        return redirect(url_for('loginForm'))
    else:
        login, userid = True, session['userid']
    cats = []
    try:
        sql = '''SELECT b.BookID,
                        b.BookTitle,
                        b.BookAuthor,
                        floor((b.PubilcationYear - 1000) / 10),
                        b.ImageM
                 FROM Cart a
                          LEFT JOIN Books b on a.BookID = b.BookID
                 WHERE a.UserID = %s'''
        cats = mysql.fetchall_db(sql, (userid,))
        cats = [[v for k, v in row.items()] for row in cats]
    except Exception as e:
        logger.exception("order error: {}".format(e))
    return render_template("Order.html",
                           books=cats,
                           login=login,
                           useid=userid)


@app.route("/addcart", methods=['GET'])
def addcart():
    """添加购物车"""
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']
    try:
        bookid = request.args.get('bookid')
        if not bookid:
            return redirect(url_for('order'))

        # 检查是否已在购物车
        sql_check = '''SELECT COUNT(1) as count \
                       FROM Cart \
                       WHERE UserID=%s \
                         and BookID=%s'''
        count = mysql.fetchone_db(sql_check, (userid, bookid))

        if not count or count['count'] == 0:
            sql_insert = '''INSERT INTO Cart (UserID, BookID) \
                            values (%s, %s)'''
            mysql.exe(sql_insert, (userid, bookid))
            logger.info(f"add cart success: user={userid}, book={bookid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("add cart error: {}".format(e))
    return redirect(url_for('order'))


@app.route("/delete", methods=['GET'])
def delete():
    """删除购物车商品"""
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']
    try:
        bookid = request.args.get('bookid')
        if bookid:
            sql = '''DELETE \
                     FROM Cart \
                     WHERE UserID = %s \
                       and BookID = %s'''
            mysql.exe(sql, (userid, bookid))
            logger.info(f"delete cart success: user={userid}, book={bookid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("delete cart error: {}".format(e))
    return redirect(url_for('order'))


# =============================
# 管理员相关路由
# =============================
@app.route("/admin")
def admin():
    """后台管理主页面"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))
    return render_template('Admin.html', userid="admin")


@app.route("/adminuser")
def adminuser():
    """管理用户页面"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    users = []
    try:
        sql = "select UserID, Location, Age from User where Age != 'nan' limit 20 "
        users = mysql.fetchall_db(sql)
        users = [[v for k, v in row.items()] for row in users]
    except Exception as e:
        logger.exception("adminuser error: {}".format(e))
        return render_template('AdminUser.html', users=[], error=True, userid="admin")
    return render_template('AdminUser.html', users=users, error=False, userid="admin")


@app.route("/keyword", methods=["POST"])
def keyword():
    """关键字查询用户"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    users = []
    try:
        keyword = request.form.get('keyword', '').strip()
        if keyword:
            sql = "select UserID,Location,Age from User where Location like %s limit 20 "
            users = mysql.fetchall_db(sql, (f'%{keyword}%',))
            users = [[v for k, v in row.items()] for row in users]
    except Exception as e:
        logger.exception("keyword error: {}".format(e))
    return render_template('AdminUser.html', users=users, userid="admin")


@app.route("/delete_user", methods=['GET'])
def delete_user():
    """删除用户"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    try:
        userid = request.args.get('userid')
        if userid:
            sql = '''DELETE \
                     FROM User \
                     WHERE UserID = %s'''
            mysql.exe(sql, (userid,))
            logger.info(f"delete user success: {userid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("delete user error: {}".format(e))
    return redirect(url_for('adminuser'))


@app.route("/adminbook")
def adminbook():
    """管理书籍页面"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    books = []
    try:
        sql = "select BookID, BookTitle, BookAuthor, PubilcationYear, ImageM from Books limit 20 "
        books = mysql.fetchall_db(sql)
        books = [[v for k, v in row.items()] for row in books]
    except Exception as e:
        logger.exception("adminbook error: {}".format(e))
    return render_template('AdminBook.html', books=books, userid="admin")


@app.route("/keyword_book", methods=["POST"])
def keyword_book():
    """关键字查询书籍"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    books = []
    try:
        keyword = request.form.get('keyword', '').strip()
        if keyword:
            sql = "select BookID, BookTitle, BookAuthor, PubilcationYear, ImageM from Books where BookTitle like %s limit 20 "
            books = mysql.fetchall_db(sql, (f'%{keyword}%',))
            books = [[v for k, v in row.items()] for row in books]
    except Exception as e:
        logger.exception("keyword_book error: {}".format(e))
    return render_template('AdminBook.html', books=books, userid="admin")


@app.route("/delete_book", methods=['GET'])
def delete_book():
    """删除书籍"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    try:
        bookid = request.args.get('bookid')
        if bookid:
            # 先删除关联数据
            mysql.exe("DELETE FROM Booktuijian WHERE BookID=%s", (bookid,))
            mysql.exe("DELETE FROM Bookrating WHERE BookID=%s", (bookid,))
            mysql.exe("DELETE FROM Cart WHERE BookID=%s", (bookid,))
            # 删除书籍
            sql = '''DELETE \
                     FROM Books \
                     WHERE BookID = %s'''
            mysql.exe(sql, (bookid,))
            logger.info(f"delete book success: {bookid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("delete book error: {}".format(e))
    return redirect(url_for('adminbook'))


@app.route("/addbook", methods=['POST'])
def addbook():
    """添加书籍"""
    if session.get('userid') != 'admin':
        return redirect(url_for('loginForm'))

    try:
        bookid = request.form.get('bookid', '').strip()
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        public = request.form.get('public', '').strip()

        if not all([bookid, title, author]):
            return render_template('AdminBook.html', error="参数不完整", books=[], userid="admin")

        # 检查书籍是否已存在
        check_sql = "SELECT BookID FROM Books WHERE BookID=%s"
        if mysql.fetchone_db(check_sql, (bookid,)):
            return render_template('AdminBook.html', error="书籍ID已存在", books=[], userid="admin")

        # 插入新书籍
        sql = """INSERT INTO Books (BookID, BookTitle, BookAuthor, PubilcationYear)
                 VALUES (%s, %s, %s, %s)"""
        mysql.exe(sql, (bookid, title, author, public))
        logger.info(f"add book success: {bookid} - {title}")
    except Exception as e:
        mysql.rollback()
        logger.exception("add book error: {}".format(e))
        return render_template('AdminBook.html', error="添加失败", books=[], userid="admin")
    return redirect(url_for('adminbook'))


# =============================
# 个人信息修改路由
# =============================
@app.route("/editinfo", methods=["POST"])
def editinfo():
    """修改个人信息"""
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']
    try:
        password = request.form.get('password', '').strip()
        age = request.form.get('age', '').strip()

        if not password or not age.isdigit():
            return redirect(url_for('user'))

        sql = "UPDATE User SET Location=%s, Age=%s WHERE UserID=%s"
        mysql.exe(sql, (password, age, userid))
        logger.info(f"update user info success: {userid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("editinfo error: {}".format(e))
    return redirect(url_for('user'))


@app.route("/editpassword", methods=["POST"])
def editpassword():
    """修改密码"""
    if 'userid' not in session:
        return redirect(url_for('loginForm'))

    userid = session['userid']
    try:
        password1 = request.form.get('password1', '').strip()
        password2 = request.form.get('password2', '').strip()

        if password1 and password1 == password2:
            sql = "UPDATE User SET Location=%s WHERE UserID=%s"
            mysql.exe(sql, (password1, userid))
            logger.info(f"update password success: {userid}")
    except Exception as e:
        mysql.rollback()
        logger.exception("editpassword error: {}".format(e))
    return redirect(url_for('user'))


# =============================
# 搜索路由
# =============================
@app.route("/search", methods=['GET'])
def search():
    """书籍搜索"""
    login, userid = False, None
    if 'userid' in session:
        login, userid = True, session['userid']

    keyword, search_books = "", []
    try:
        keyword = request.args.get('keyword', '').strip()
        if keyword:
            sql = "SELECT BookTitle, BookAuthor, BookID, ImageM from Books where BookTitle like %s limit 20"
            search_books = mysql.fetchall_db(sql, (f'%{keyword}%',))
            search_books = [[v for k, v in row.items()] for row in search_books]
    except Exception as e:
        logger.exception("search error: {}".format(e))
    return render_template("Search.html",
                           key=keyword,
                           books=search_books,
                           login=login,
                           useid=userid)


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
