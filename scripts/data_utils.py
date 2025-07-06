import os
import json
import re
import ast
def extract_class_names(code: str):
    """
    Trả về danh sách tên tất cả các class trong đoạn code.
    """
    try:
        # Thử parse trực tiếp
        tree = ast.parse(code)
        class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        return class_names
    except (IndentationError, SyntaxError):
        # Nếu có lỗi indentation, thử fix bằng cách normalize indentation
        try:
            # Normalize indentation - loại bỏ thụt lề không hợp lệ
            lines = code.split('\n')
            normalized_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    # Tìm indentation level hợp lệ
                    indent_level = 0
                    for char in line:
                        if char == ' ':
                            indent_level += 1
                        elif char == '\t':
                            indent_level += 4  # Convert tab to spaces
                        else:
                            break
                    # Normalize thành 4 spaces per level
                    normalized_indent = '    ' * (indent_level // 4)
                    normalized_lines.append(normalized_indent + stripped)
                else:
                    normalized_lines.append('')
            
            normalized_code = '\n'.join(normalized_lines)
            tree = ast.parse(normalized_code)
            class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            return class_names
        except (IndentationError, SyntaxError):
            # Nếu vẫn lỗi, trả về empty list
            return []

def find_enclosing_def_class(code: str, lineno: int):
    """
    Trả về tuple (class_name, func_name) chứa dòng `lineno` trong code.
    Nếu không nằm trong class hoặc func nào thì trả về None.
    """
    tree = ast.parse(code)
    class_name = None
    func_name = None

    def visit(node, parents):
        nonlocal class_name, func_name
        # Kiểm tra node có thuộc dòng cần tìm không
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
            if node.lineno <= lineno <= node.end_lineno:
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
        for child in ast.iter_child_nodes(node):
            visit(child, parents + [node])

    # Đầu tiên cần gán end_lineno cho node nếu dùng Python <3.8
    ast.increment_lineno(tree, 0)
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if not hasattr(child, 'end_lineno'):
                child.end_lineno = getattr(child, 'lineno', None)

    visit(tree, [])
    return class_name, func_name
def fix_line_breaks_in_code(code: str) -> str:
    """
    Xóa toàn bộ comment (bao gồm cả docstring), sau đó gộp các dòng code bị xuống dòng không hợp lý, bao gồm cả các biểu thức dài trong dấu ngoặc ((), [], {}).
    Ví dụ:
    return (
        a or
        b
    )
    => return (a or b)
    """
    import re
    # Xóa docstring ("""...""" hoặc '''...''')
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    # Xóa comment ở cuối dòng và các dòng chỉ chứa comment
    code_no_comment = []
    for line in code.split('\n'):
        # Bỏ dòng chỉ chứa comment hoặc rỗng
        if re.match(r'^\s*#', line) or line.strip() == '':
            continue
        # Xóa comment ở cuối dòng (không nằm trong chuỗi)
        # Đơn giản: tách theo # đầu tiên nếu không nằm trong chuỗi
        def remove_inline_comment(s):
            in_single = in_double = False
            for i, c in enumerate(s):
                if c == '"' and not in_single:
                    in_double = not in_double
                elif c == "'" and not in_double:
                    in_single = not in_single
                elif c == '#' and not in_single and not in_double:
                    return s[:i].rstrip()
            return s
        code_no_comment.append(remove_inline_comment(line))
    code = '\n'.join(code_no_comment)

    lines = code.split('\n')
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Nếu dòng bắt đầu bằng dấu ngoặc mở hoặc có dấu ngoặc mở chưa đóng
        if re.search(r'\($|\[$|\{$', line.strip()) or (
            line.count('(') > line.count(')') or
            line.count('[') > line.count(']') or
            line.count('{') > line.count('}')
        ):
            open_paren = line.count('(') - line.count(')')
            open_brack = line.count('[') - line.count(']')
            open_brace = line.count('{') - line.count('}')
            expr = line.strip()
            j = i + 1
            while j < len(lines) and (open_paren > 0 or open_brack > 0 or open_brace > 0):
                next_line = lines[j].strip()
                expr += ' ' + next_line
                open_paren += next_line.count('(') - next_line.count(')')
                open_brack += next_line.count('[') - next_line.count(']')
                open_brace += next_line.count('{') - next_line.count('}')
                j += 1
            fixed_lines.append(expr)
            i = j
        else:
            # Gộp các dòng điều kiện bị tách không hợp lý
            while i + 1 < len(lines):
                next_line = lines[i + 1].lstrip()
                if re.match(r'^(and|or|else|elif|except|finally|\)|\]|\}|[+\-*/%&|^.,:<>!=])', next_line):
                    line += ' ' + next_line
                    i += 1
                else:
                    break
            fixed_lines.append(line)
            i += 1
    return '\n'.join(fixed_lines)

# Ví dụ sử dụng


def find_path_from_target_to_root(code, target_lineno):
    """
    Trả về list các số dòng (lineno) từ node có target_lineno lên tới root trong AST.
    Nếu không tìm thấy node nào có lineno == target_lineno, trả về None.
    """
    tree = ast.parse(code)
    parent_map = {}
    target_node = None

    # Duyệt cây để xây parent_map và tìm node target
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[child] = node
        if hasattr(node, 'lineno') and node.lineno == target_lineno:
            target_node = node

    if target_node is None:
        return None

    # Truy vết từ target_node lên root
    path = []
    node = target_node
    while node in parent_map:
        if hasattr(node, 'lineno'):
            path.append(node.lineno)
        node = parent_map[node]
    # Thêm root nếu có lineno
    if hasattr(node, 'lineno'):
        path.append(node.lineno)
    return path[::-1]  # Đường đi từ root đến target

def similarity(a,b):
    """Compute similarity between two lists."""
    # Xử lý trường hợp a hoặc b là None
    if a is None or b is None:
        return 0.0
    
    a_set = set(a)
    b_set = set(b)
    test_good = None
    execution_good = None
    intersection = a_set.intersection(b_set)
    
    # Tránh division by zero
    if len(b_set) == 0:
        return 0.0
    
    return len(intersection) / len(b_set)
def solve(result_execute, code, target_line):
    max_threhold = 0
    path_target = find_path_from_target_to_root(code, target_line)
    test_good = None
    best = None
    execution_good = None
    
    # Xử lý trường hợp path_target là None
    if path_target is None:
        return None, None, None, 0.0
    
    for i, item in enumerate(result_execute):
        simi = similarity(item['executed_lines'], path_target)
        if simi >= max_threhold:
            best = i
            max_threhold = simi 
            test_good = item['test']
            execution_good = item['executed_lines']
    return best, test_good, execution_good, max_threhold

def extract_python_code_block(text):
    # Tìm đoạn code nằm trong ```python ... ```
    pattern = r"```python\s*([\s\S]*?)```"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""
def extract_line(code, line):
    code_line = code.split('\n')
    return code_line[line-1]

def extract_test_func(code, func_name):
    # Tìm từ def test_func_name() đến hết file hoặc đến dòng không thụt lề
    pattern = rf"(def test_{func_name}\s*\([\s\S]*?)(?=^def |\Z)"
    match = re.search(pattern, code, re.MULTILINE)
    test_func = ""
    if match:
        test_func = match.group(1).strip()
    # Tìm dòng gọi test ở ngoài (không nằm trong thân hàm)
    lines = code.splitlines()
    call_line = f"{func_name}()"
    call_found = False
    for line in lines:
        if line.strip() == call_line:
            call_found = True
            break
    if call_found and not test_func.endswith(call_line):
        test_func += "\n" + call_line
    return test_func

def seg_code_divide_class(code: str):
    """
    Trả về list các đoạn code class (dạng string) trong code đầu vào.
    """
    try:
        tree = ast.parse(code)
        class_segments = []
        lines = code.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                # Tìm dòng kết thúc class (dựa vào node.end_lineno nếu có, hoặc tự tìm)
                end = getattr(node, 'end_lineno', None)
                if end is None:
                    # Nếu Python <3.8 không có end_lineno, tìm thủ công
                    # Lấy tất cả dòng đến khi gặp class/def cùng cấp hoặc hết file
                    end = start + 1
                    indent = len(lines[start]) - len(lines[start].lstrip())
                    for i in range(start + 1, len(lines)):
                        line = lines[i]
                        if line.strip() == "":
                            continue
                        if len(line) - len(line.lstrip()) <= indent and (line.lstrip().startswith('class ') or line.lstrip().startswith('def ')):
                            break
                        end = i + 1
                class_code = ''.join(lines[start:end])
                class_segments.append(class_code)
        return class_segments
    except (IndentationError, SyntaxError) as e:
        # Nếu có lỗi parse, trả về empty list
        print(f"Warning: Cannot parse code for class segmentation: {e}")
        return []

def read_jsonl(path):
    data=[]
    with open(path,'r') as f:
        for line in f:
            data.append(json.loads(line))
    return data
def code_in_line(code):
    """Add line numbers to code."""
    lines=code.split('\n')
    new_code=''
    for i, line in enumerate(lines):
        new_code+=f'{i+1}. {line}\n'
    return new_code
def extract(code, target_line):
    code = code_in_line(code)
    final_code = ''
    for i, line in enumerate(code.split('\n')):
        if i == target_line:
            return final_code
        final_code+=f'{line}\n'
    return final_code

def write_jsonl(data,path):
    with open(path,'w') as f:
        for d in data:
            f.write(json.dumps(d)+'\n')
def line_code(code):
    """Trả về danh sách số dòng chứa code logic thực sự, loại bỏ dòng trống, import, def, class, v.v."""
    lines = code.split('\n')
    line_numbers = []
    
    i = 0
    in_multiline_comment = False
    multiline_delim = None
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Xử lý bắt đầu/kết thúc comment nhiều dòng
        if not in_multiline_comment:
            cond1 = stripped.startswith("'''") and not stripped.endswith("'''")
            cond2 = stripped.startswith('"""') and not stripped.endswith('"""')
            cond3 = stripped.startswith('###') and not stripped.endswith('###')
            if cond1 or cond2 or cond3:
                in_multiline_comment = True
                if stripped.startswith("'''"):
                    multiline_delim = "'''"
                elif stripped.startswith('"""'):
                    multiline_delim = '"""'
                else:
                    multiline_delim = '###'
                i += 1
                continue
            # Trường hợp comment nhiều dòng trên 1 dòng
            cond4 = stripped.startswith("'''") and stripped.endswith("'''") and len(stripped) > 3
            cond5 = stripped.startswith('"""') and stripped.endswith('"""') and len(stripped) > 3
            cond6 = stripped.startswith('###') and stripped.endswith('###') and len(stripped) > 3
            if cond4 or cond5 or cond6:
                i += 1
                continue
        else:
            # Đang trong block comment nhiều dòng
            if multiline_delim and multiline_delim in stripped:
                in_multiline_comment = False
                multiline_delim = None
            i += 1
            continue

        # Bỏ qua dòng trống
        if not stripped:
            i += 1
            continue
            
        # Bỏ qua comment
        if stripped.startswith('#'):
            i += 1
            continue
            
        # Bỏ qua docstring
        if stripped.startswith('"""') or stripped.startswith("'''"):
            i += 1
            continue
            
        # Bỏ qua import statements
        if stripped.startswith('import ') or stripped.startswith('from '):
            i += 1
            continue
            
        # Bỏ qua def, class declarations (chỉ lấy thân hàm/class)
        if stripped.startswith('def ') or stripped.startswith('class '):
            i += 1
            continue
            
        # Bỏ qua decorators
        if stripped.startswith('@'):
            i += 1
            continue
            
        # Bỏ qua pass statements
        if stripped == 'pass':
            i += 1
            continue
            
        # Bỏ qua return statements đơn giản
        if stripped == 'return' or stripped == 'return None':
            i += 1
            continue
            
        # Bỏ qua else:, except:, finally: đơn giản
        if stripped in ['else:', 'except:', 'finally:', 'elif:']:
            i += 1
            continue
            
        # Bỏ qua dòng chỉ có dấu ngoặc
        if stripped in ['{', '}', '[', ']', '(', ')']:
            i += 1
            continue
        
        # Kiểm tra xem có phải là dòng continuation của câu lệnh trước không
        current_indent = len(line) - len(line.lstrip())
        
        # Kiểm tra xem dòng trước có kết thúc bằng dấu phẩy, dấu ngoặc mở, hoặc dấu backslash không
        is_continuation = False
        if i > 0:
            prev_line = lines[i-1].strip()
            prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
            
            # Chỉ coi là continuation nếu:
            # 1. Dòng trước kết thúc bằng dấu continuation và dòng hiện tại có indent lớn hơn
            # 2. Hoặc dòng hiện tại có indent lớn hơn đáng kể (thuộc block con)
            if ((prev_line.endswith(',') or 
                 prev_line.endswith('(') or 
                 prev_line.endswith('[') or 
                 prev_line.endswith('{') or
                 prev_line.endswith('\\')) and 
                current_indent > prev_indent):
                is_continuation = True
        
        # Nếu đây là dòng đầu tiên của câu lệnh hoặc dòng có logic thực sự
        # (không phải continuation line)
        if not is_continuation:
            # Thêm dòng này vào kết quả
            line_numbers.append(i + 1)
        
        i += 1
    
    return line_numbers

def add_lineno(code):
    """Add line numbers to code."""
    lines=code.split('\n')
    new_code=''
    for i, line in enumerate(lines):
        new_code+=f'{i+1}. {line}\n'
    return new_code


def add_lineno_comment(code,docstring_lines=None):
    """Add line numbers to code as comments."""
    lines=code.split('\n')
    for i in range(len(lines)-1,-1,-1):
        if lines[i]=='':
            lines.pop(i)
        else:
            break
    new_code=''
    if docstring_lines is None:
        for i, line in enumerate(lines):
            if i == len(lines) - 1:
                new_code+=f'{line}  #{i+1}'
            else:
                new_code+=f'{line}  #{i+1}\n'
    else:
        docstart,docend=docstring_lines
        for i, line in enumerate(lines):
            if i>=docstart and i<=docend:
                new_code+=f'{line}\n'
            else:
                if i == len(lines) - 1:
                    new_code+=f'{line}  #{i+1}'
                else:
                    new_code+=f'{line}  #{i+1}\n'
    return new_code
def line_code1(code):
    """Trả về danh sách số dòng chứa code logic thực sự, nhưng KHÔNG bỏ qua các dòng import, if, else, ..."""
    lines = code.split('\n')
    line_numbers = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Bỏ qua dòng trống
        if not stripped:
            i += 1
            continue
        # Bỏ qua comment
        if stripped.startswith('#'):
            i += 1
            continue
        # Bỏ qua docstring
        if stripped.startswith('"""') or stripped.startswith("'''"):
            i += 1
            continue
        # Bỏ qua decorators
        if stripped.startswith('@'):
            i += 1
            continue
        # Bỏ qua pass statements
        if stripped == 'pass':
            i += 1
            continue
        # Bỏ qua return statements đơn giản
        if stripped == 'return' or stripped == 'return None':
            i += 1
            continue
        # Bỏ qua dòng chỉ có dấu ngoặc
        if stripped in ['{', '}', '[', ']', '(', ')']:
            i += 1
            continue
        # Kiểm tra xem có phải là dòng continuation của câu lệnh trước không
        current_indent = len(line) - len(line.lstrip())
        is_continuation = False
        if i > 0:
            prev_line = lines[i-1].strip()
            prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
            if ((prev_line.endswith(',') or 
                 prev_line.endswith('(') or 
                 prev_line.endswith('[') or 
                 prev_line.endswith('{') or
                 prev_line.endswith('\\')) and 
                current_indent > prev_indent):
                is_continuation = True
        if not is_continuation:
            line_numbers.append(i + 1)
        i += 1
    return line_numbers
