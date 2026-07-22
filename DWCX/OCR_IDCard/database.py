import pymysql
import os
import uuid

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'id_card',
    'charset': 'utf8mb4',
    'port': 3306
}

def get_connection():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"数据库连接失败: {str(e)}")
        return None

def init_db():
    conn = get_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT uid FROM id_cards LIMIT 1')
        has_uid = True
    except Exception:
        has_uid = False
    
    if not has_uid:
        cursor.execute('DROP TABLE IF EXISTS id_cards')
        cursor.execute('''
            CREATE TABLE id_cards (
                id INT PRIMARY KEY AUTO_INCREMENT,
                uid VARCHAR(36) UNIQUE NOT NULL COMMENT '随机生成的唯一ID',
                image LONGBLOB NOT NULL,
                image_name VARCHAR(255),
                name VARCHAR(100),
                id_number VARCHAR(18),
                gender VARCHAR(10),
                nationality VARCHAR(50),
                address TEXT,
                issue_authority VARCHAR(200),
                valid_period VARCHAR(50),
                valid_type VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ''')
    
    try:
        cursor.execute('ALTER TABLE id_cards ADD INDEX IF NOT EXISTS idx_issue_authority (issue_authority)')
        cursor.execute('ALTER TABLE id_cards ADD INDEX IF NOT EXISTS idx_valid_type (valid_type)')
        cursor.execute('ALTER TABLE id_cards ADD INDEX IF NOT EXISTS idx_valid_period (valid_period)')
        cursor.execute('ALTER TABLE id_cards ADD INDEX IF NOT EXISTS idx_created_at (created_at)')
    except Exception as e:
        print(f"创建索引失败（可能已存在）: {str(e)}")
    
    conn.commit()
    conn.close()
    return True

def generate_uid():
    return str(uuid.uuid4())

def check_duplicate(issue_authority, valid_period):
    conn = get_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id FROM id_cards 
            WHERE issue_authority = %s AND valid_period = %s
            LIMIT 1
        ''', (issue_authority, valid_period))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print(f"检查重复失败: {str(e)}")
        conn.close()
        return False

def add_id_card(image_data, image_name, name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type):
    conn = get_connection()
    if not conn:
        print("数据库连接失败")
        return None
    
    cursor = conn.cursor()
    
    try:
        if issue_authority and valid_period:
            if check_duplicate(issue_authority, valid_period):
                print(f"重复数据：签发机关={issue_authority}, 有效期限={valid_period}，已存在，跳过插入")
                conn.close()
                return {'id': -1, 'uid': '', 'duplicate': True}
        
        uid = generate_uid()
        print(f"准备插入数据: uid={uid}, name={name}, id_number={id_number}, issue_authority={issue_authority}, valid_period={valid_period}, valid_type={valid_type}")
        
        cursor.execute('''
            INSERT INTO id_cards (uid, image, image_name, name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (uid, image_data, image_name, name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type))
        
        conn.commit()
        card_id = cursor.lastrowid
        print(f"插入成功，序号: {card_id}, UID: {uid}")
        conn.close()
        return {'id': card_id, 'uid': uid}
    except Exception as e:
        print(f"插入数据失败: {str(e)}")
        conn.rollback()
        conn.close()
        return None

def get_all_id_cards(page=1, page_size=20):
    conn = get_connection()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    offset = (page - 1) * page_size
    cursor.execute('''
        SELECT id, uid, image_name, name, id_number, gender, nationality, 
               address, issue_authority, valid_period, valid_type, created_at 
        FROM id_cards 
        ORDER BY created_at DESC 
        LIMIT %s OFFSET %s
    ''', (page_size, offset))
    rows = cursor.fetchall()
    
    conn.close()
    return rows

def get_total_count():
    conn = get_connection()
    if not conn:
        return 0
    
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM id_cards')
    row = cursor.fetchone()
    
    conn.close()
    return row[0] if row else 0

def get_id_card_by_id(card_id):
    conn = get_connection()
    if not conn:
        return None
    
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM id_cards WHERE id = %s', (card_id,))
    row = cursor.fetchone()
    
    conn.close()
    return row

def update_id_card(card_id, name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type):
    conn = get_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE id_cards 
            SET name = %s, id_number = %s, gender = %s, nationality = %s, address = %s, 
                issue_authority = %s, valid_period = %s, valid_type = %s
            WHERE id = %s
        ''', (name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type, card_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"更新数据失败: {str(e)}")
        conn.rollback()
        conn.close()
        return False

def delete_id_card(card_id):
    conn = get_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM id_cards WHERE id = %s', (card_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"删除数据失败: {str(e)}")
        conn.rollback()
        conn.close()
        return False

def search_cards(issue_authority=None, valid_type=None, page=1, page_size=20):
    conn = get_connection()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    query = 'SELECT id, uid, image_name, name, id_number, gender, nationality, address, issue_authority, valid_period, valid_type, created_at FROM id_cards WHERE 1=1'
    params = []
    
    if issue_authority and issue_authority.strip():
        query += ' AND issue_authority LIKE %s'
        params.append(f'%{issue_authority.strip()}%')
    
    if valid_type and valid_type.strip():
        query += ' AND valid_type = %s'
        params.append(valid_type.strip())
    
    query += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
    offset = (page - 1) * page_size
    params.extend([page_size, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    conn.close()
    return rows

def search_cards_count(issue_authority=None, valid_type=None):
    conn = get_connection()
    if not conn:
        return 0
    
    cursor = conn.cursor()
    
    query = 'SELECT COUNT(*) FROM id_cards WHERE 1=1'
    params = []
    
    if issue_authority and issue_authority.strip():
        query += ' AND issue_authority LIKE %s'
        params.append(f'%{issue_authority.strip()}%')
    
    if valid_type and valid_type.strip():
        query += ' AND valid_type = %s'
        params.append(valid_type.strip())
    
    cursor.execute(query, params)
    row = cursor.fetchone()
    
    conn.close()
    return row[0] if row else 0

def get_image_data(card_id):
    conn = get_connection()
    if not conn:
        return None
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT image FROM id_cards WHERE id = %s', (card_id,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"获取图片数据失败: {str(e)}")
        conn.close()
        return None

def download_image(card_id, save_path):
    conn = get_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT image, image_name FROM id_cards WHERE id = %s', (card_id,))
        row = cursor.fetchone()
        
        if row:
            image_data = row[0]
            with open(save_path, 'wb') as f:
                f.write(image_data)
            conn.close()
            return True
        else:
            conn.close()
            return False
    except Exception as e:
        print(f"下载图片失败: {str(e)}")
        conn.close()
        return False

def get_all_issue_authorities():
    conn = get_connection()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    cursor.execute('SELECT DISTINCT issue_authority FROM id_cards WHERE issue_authority IS NOT NULL AND issue_authority != "" ORDER BY issue_authority')
    rows = cursor.fetchall()
    
    conn.close()
    return [row[0] for row in rows]