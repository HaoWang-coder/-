import re

def parse_id_card_info(texts):
    info = {
        'name': '',
        'id_number': '',
        'gender': '',
        'nationality': '',
        'address': '',
        'issue_authority': '',
        'valid_period': '',
        'valid_type': ''
    }
    
    full_text = '\n'.join(texts)
    
    print(f"识别到的文本: {full_text}")
    
    name_match = re.search(r'(姓\s*名|姓名)\s*[：:]\s*([\u4e00-\u9fa5]{2,4})', full_text)
    if name_match:
        info['name'] = name_match.group(2).strip()
    
    id_match = re.search(r'(公民身份号码|身份证号)\s*[：:]\s*(\d{18})', full_text)
    if not id_match:
        id_match = re.search(r'\b\d{17}[\dXx]\b', full_text)
    if id_match:
        info['id_number'] = id_match.group(1) if id_match.lastindex == 1 else id_match.group()
    
    gender_match = re.search(r'(性\s*别|性别)\s*[：:]\s*(男|女)', full_text)
    if not gender_match and info['id_number']:
        gender_code = int(info['id_number'][16])
        info['gender'] = '男' if gender_code % 2 == 1 else '女'
    elif gender_match:
        info['gender'] = gender_match.group(2).strip()
    
    nationality_match = re.search(r'(民\s*族|民族)\s*[：:]\s*([\u4e00-\u9fa5]+)', full_text)
    if nationality_match:
        info['nationality'] = nationality_match.group(2).strip()
    
    address_match = re.search(r'(住址|地址)\s*[：:]\s*([\u4e00-\u9fa50-9省市区县镇村街道路号]+)', full_text)
    if address_match:
        info['address'] = address_match.group(2).strip()
    
    authority_patterns = [
        r'(签发机关|发证机关)\s*[：:]\s*([\u4e00-\u9fa5]+[公安局|派出所|分局]+[\u4e00-\u9fa5]*)',
        r'(签发机关|发证机关)\s*[：:]\s*([\u4e00-\u9fa5]+[公安局|派出所]+)',
        r'([\u4e00-\u9fa5]+[公安局|派出所|分局]+[\u4e00-\u9fa5]*)',
        r'([\u4e00-\u9fa5]+[公安局|派出所]+)'
    ]
    
    authority_match = None
    for pattern in authority_patterns:
        authority_match = re.search(pattern, full_text)
        if authority_match:
            break
    
    if authority_match:
        if authority_match.lastindex == 2:
            info['issue_authority'] = authority_match.group(2).strip()
        else:
            info['issue_authority'] = authority_match.group().strip()
    
    if info['issue_authority']:
        info['issue_authority'] = re.sub(r'^签发机关\s*', '', info['issue_authority'])
        info['issue_authority'] = re.sub(r'^发证机关\s*', '', info['issue_authority'])
        info['issue_authority'] = info['issue_authority'].strip()
    
    period_match = re.search(r'(有效期限|有效期至|有效期|期限)\s*[：:]\s*(\d{4}\.\d{2}\.\d{2})[-至~–—](\d{4}\.\d{2}\.\d{2})', full_text)
    if not period_match:
        period_match = re.search(r'(\d{4})\s*[\.\-/年]\s*(\d{1,2})\s*[\.\-/月]\s*(\d{1,2})\s*[-至~–—]\s*(\d{4})\s*[\.\-/年]\s*(\d{1,2})\s*[\.\-/月]\s*(\d{1,2})', full_text)
    if not period_match:
        period_match = re.search(r'(\d{4}\.\d{2}\.\d{2})[-至~–—](\d{4}\.\d{2}\.\d{2})', full_text)
    if not period_match:
        period_match = re.search(r'(\d{4}-\d{2}-\d{2})[-至~–—](\d{4}-\d{2}-\d{2})', full_text)
    if not period_match:
        period_match = re.search(r'(\d{4})\.\s*(\d{2})\.\s*(\d{2}).*(\d{4})\.\s*(\d{2})\.\s*(\d{2})', full_text)
    
    if period_match:
        if period_match.lastindex == 6:
            info['valid_period'] = f"{period_match.group(1)}.{period_match.group(2)}.{period_match.group(3)}-{period_match.group(4)}.{period_match.group(5)}.{period_match.group(6)}"
        elif period_match.lastindex == 3:
            info['valid_period'] = f"{period_match.group(2)}-{period_match.group(3)}"
        elif period_match.lastindex == 2:
            info['valid_period'] = f"{period_match.group(1)}-{period_match.group(2)}"
        else:
            info['valid_period'] = period_match.group()
    
    if info['valid_period']:
        info['valid_period'] = info['valid_period'].strip()
    
    long_term_match = re.search(r'(长期|永久)', full_text)
    if long_term_match or (info['valid_period'] and ('长期' in info['valid_period'] or '永久' in info['valid_period'])):
        info['valid_type'] = '长期'
        if not info['valid_period']:
            info['valid_period'] = '长期'
    elif info['valid_period']:
        try:
            dates = re.findall(r'\d{4}', info['valid_period'])
            if len(dates) >= 2:
                years = int(dates[1]) - int(dates[0])
                if years >= 20:
                    info['valid_type'] = '20年'
                elif years >= 10:
                    info['valid_type'] = '10年'
                else:
                    info['valid_type'] = '5年'
            else:
                info['valid_type'] = '10年'
        except Exception as e:
            print(f"计算有效期类型失败: {e}")
            info['valid_type'] = '10年'
    else:
        info['valid_type'] = '10年'
    
    print(f"解析结果: {info}")
    return info