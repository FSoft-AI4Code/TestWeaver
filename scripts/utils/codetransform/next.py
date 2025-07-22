from __future__ import annotations
import textwrap
import sys
from utils.codetransform import trace_execution
import copy
from types import FunctionType

class ExecutionTracer:
    def __init__(self):
        self.tracer = trace_execution.Trace(count=False, trace=True, countfuncs=False, countcallers=False)
        self.execution_trace = []
        self.idx = 0
        self.error = None
        self.asserterror = False

    def trace_execution(self, frame, event, arg):
        if not frame.f_code.co_filename.endswith("next.py"):
             return self.trace_execution
        if '__builtins__' not in frame.f_locals and ".0" not in frame.f_locals and len(frame.f_locals) > 0 and 'module' not in frame.f_locals:
            code = frame.f_code
            lineno = frame.f_lineno
            locals_snapshot = {}
            for k, v in frame.f_locals.items():
                if isinstance(v, (int, float, str, bool, list, dict, set, tuple, type(None))):
                    try:
                        locals_snapshot[k] = copy.deepcopy(v)
                    except Exception:
                        locals_snapshot[k] = v
                else:
                    locals_snapshot[k] = f"<{type(v).__name__} object>"
            self.execution_trace.append([lineno, locals_snapshot])
        return self.trace_execution

    def start_tracing(self, code):
        sys.settrace(self.trace_execution)
        try:
            exec(code, {})
        except AssertionError as e:
            self.error = e
            self.asserterror = True
        except Exception as e:
            self.error = e
        sys.settrace(None)

    def get_execution_trace(self):
        return self.execution_trace

def generate_commented_code(source, in_line_cmt):
    code_lines = source.split('\n')
    code_lines = [element.rstrip() for element in code_lines]
    commented_code = []

    for lineno, line in enumerate(code_lines, 1):     #vị trí và code ở line đó
        if lineno in in_line_cmt:
            comments = in_line_cmt[lineno]
            
            if comments:
                first_comment = comments[0]
                last_comment = comments[-1]

                # Handle NO_CHANGE scenario
                if isinstance(first_comment[1], str):
                    first_comment_str = f"({first_comment[0]}) {first_comment[1]}"
                else:
                    first_comment_str = f"({first_comment[0]}) " + "; ".join([f"{k}={v}" for k, v in first_comment[1].items()])
                
                if first_comment == last_comment:
                    inline_comment = f" # {first_comment_str}"
                else:
                    if isinstance(last_comment[1], str):
                        last_comment_str = f"({last_comment[0]}) {last_comment[1]}"
                    else:
                        last_comment_str = f"({last_comment[0]}) " + "; ".join([f"{k}={v}" for k, v in last_comment[1].items()])
                    
                    inline_comment = f" # {first_comment_str}; ...; {last_comment_str}"
                
                commented_code.append(line + inline_comment)
            else:
                commented_code.append(line)
        else:
            commented_code.append(line)

    return "\n".join(commented_code)

def execute_and_trace(source: str):
    code_lines = source.split('\n')
    code_lines = [element.rstrip() for element in code_lines]
    try:
        code = compile(source, "next.py", 'exec')
    except SyntaxError as e:
        return f"SYNTAX ERROR: {e}"
    tracer = ExecutionTracer()
    tracer.start_tracing(code)
    execution_trace = tracer.get_execution_trace()
    # for line, snapshot in execution_trace:
    #     if (line == 155 or line ==159):
    #         print(f'-------{line}====={snapshot}\n')
    error = tracer.error
    asserterror = tracer.asserterror
    # print(execution_trace)
    intermediate_value = []
    code_line = [element.lstrip() for element in source.split("\n")]
    condition_line = []
    def_line = 0
    for i in range(len(code_line)):
        if code_line[i].startswith('if') or code_line[i].startswith('elif') or code_line[i].startswith('else'):
            condition_line.append(i+1)
        if code_line[i].startswith('assert'):
            assert_line = i+1
        if code_line[i].startswith('def'):
            if def_line == 0:
                def_line = i+1
    for i in range(len(execution_trace)-1):
        if execution_trace[i][0] not in condition_line:
            if i > 0:
                if execution_trace[i][0] == execution_trace[i-1][0]:
                    if execution_trace[i][1] == execution_trace[i-1][1]:
                        continue
            special_keys = {'__module__', '__qualname__', '__firstlineno__'}
            if all(special_key in (execution_trace[i+1][1].keys()) for special_key in special_keys):
                continue
            intermediate_value.append([execution_trace[i][0], execution_trace[i+1][1]])

    if error != None:
        if asserterror:
            intermediate_value.append([assert_line , f'__exception__ = AssertionError()'])
        else:
            if len(intermediate_value)>0:
                intermediate_value[-1][1] = f'__exception__ = {error}'
            else:
                intermediate_value.append([def_line,f'__exception__ = {error}'])
    for line, snapshot in intermediate_value:
        if (line == 155 or line ==159):
            print(f'-------{line}====={snapshot}\n')
    # print(f'--------------------------------------------- {intermediate_value} ------------------------------------')
    symbol_table = {}
    values = []
    for i in range(len(intermediate_value)):
        if i == len(intermediate_value)-1 and error ==None:
            temp_dict = {}
            for var in intermediate_value[i][1]:
                if var.startswith("__class__"):
                    continue
                if var.startswith("self"):
                    continue
                if var.startswith("__module__"):
                    continue
                if var.startswith("__qualname__"):
                    continue
                if isinstance(intermediate_value[i][1][var], FunctionType):
                    continue
                temp_dict[var] = intermediate_value[i][1][var]
            values.append([intermediate_value[i][0], temp_dict])
        elif i == len(intermediate_value)-2 and error != None:
            temp_dict = {}
            for var in intermediate_value[i][1]:
                if var.startswith("__class__"):
                    continue
                if var.startswith("self"):
                    continue
                if var.startswith("__module__"):
                    continue
                if var.startswith("__qualname__"):
                    continue
                if isinstance(intermediate_value[i][1][var], FunctionType):
                    continue
                temp_dict[var] = intermediate_value[i][1][var]
            values.append([intermediate_value[i][0], temp_dict])
        elif i == len(intermediate_value)-1 and error != None:
            values.append([intermediate_value[i][0], intermediate_value[i][1]])
        
        else:
            temp_dict = {}
            
            for var in intermediate_value[i][1]:
                if var.startswith("__class__"):
                    continue
                
                if var.startswith("self"):
                    continue
                if var.startswith("__module__"):
                    continue
                if var.startswith("__qualname__"):
                    continue
                if isinstance(intermediate_value[i][1][var], FunctionType):
                    continue
                if var not in symbol_table:
                    # print(f'===he==={var}======\n')
                    symbol_table[var] = intermediate_value[i][1][var]
                    temp_dict[var] = intermediate_value[i][1][var]
                else:
                    if symbol_table[var] != intermediate_value[i][1][var]:
                        symbol_table[var] = intermediate_value[i][1][var]
                        temp_dict[var] = intermediate_value[i][1][var]
            #### Value ở đây chi lưu những biến thay đổi hoặc những biến được thêm vào
            if len(temp_dict) > 0:
                values.append([intermediate_value[i][0], temp_dict])
            elif (i<len(code_line) and code_lines[i].lstrip().startswith("self")):
                # print(f'-----------code-----{code_line[i]}-------------\n')
                snapshot = intermediate_value[i][1]
                attr = code_lines[i].lstrip().split('=')[0].strip()
                attr = attr[len("self."):].split('[')[0].strip()
                # print(attr)
                # print(snapshot)
                if attr in snapshot:
                    temp_dict[attr] = snapshot[attr]
                    values.append([intermediate_value[i][0], temp_dict])
            # elif code_line[i].lstrip().startswith('def'):
            #     print(f'def------{code_line[i]}----------\n')
            #     continue
                
            else:
                values.append([intermediate_value[i][0], "NO_CHANGE"])

    in_line_cmt = {}
    for i in range(len(values)):
        if values[i][0] not in in_line_cmt:
            in_line_cmt[values[i][0]] = [[i, values[i][1]]]
        else:
            in_line_cmt[values[i][0]].append([i, values[i][1]])
    # print(in_line_cmt)    
    commented_code = generate_commented_code(source, in_line_cmt)

    return commented_code
def code_in_line(code):
    code_line = code.split('\n')
    final_code = ''
    for i, line in enumerate(code_line):
        final_code += f"{i+1}: {line}\n"
    return final_code
        

if __name__ == '__main__':
    source1 = textwrap.dedent("""import math

class Solution:
    def evaluate_sequence(self, arr: list[int]) -> int:
        score = 0
        freq = {}
        total = sum(arr)
        even = sum(1 for x in arr if x % 2 == 0)
        odd = len(arr) - even
        max_val = max(arr)
        min_val = min(arr)
        for x in arr:
            freq[x] = freq.get(x, 0) + 1

        if len(arr) < 4:
            if arr[0] % 2 == 0:
                score += 4
                score *= 2
                if arr[-1] % 3 == 0:
                    score += 3
                    if arr[0] == arr[-1]:
                        score += 2
                        if arr[0] ** 0.5 == int(arr[0] ** 0.5):
                            score += 1
                            if arr[0] % 4 == 0:
                                score += 2
                else:
                    if arr[0] - arr[-1] > 5:
                        score -= 1
            else:
                score -= 2
                if arr[-1] == 3:
                    score += 10
                    if 1 in arr:
                        score += 5
                        if arr.count(1) > 1:
                            score += 2
                else:
                    score += 1
                    if arr[-1] % 5 == 0:
                        score += 2
                        if freq.get(arr[-1], 0) >= 2:
                            score += 1
        elif max_val - min_val > 50:
            if total % 2 == 0:
                score += 5
                if even > odd:
                    score *= 2
                    if freq.get(100, 0) > 0:
                        score += 10
                        if arr.count(100) > 2:
                            score += 5
                            if 99 in arr:
                                score += 1
                else:
                    score -= 3
                    if arr[0] < 10:
                        score -= 2
                        prime = True
                        if arr[0] < 2:
                            prime = False
                        else:
                            for i in range(2, int(math.sqrt(arr[0])) + 1):
                                if arr[0] % i == 0:
                                    prime = False
                                    break
                        if prime:
                            score += 4
            elif freq.get(0, 0) > 0:
                score += 7
                if arr[0] == 0 and arr[-1] == 0:
                    score += 3
                    if sum(arr) == 0:
                        score += 5
            else:
                score -= 1
                if len(set(arr)) < len(arr):
                    score += 2
                    if any(v > 3 for v in freq.values()):
                        score += 1
        else:
            sorted_flag = arr == sorted(arr)
            if sorted_flag:
                score += 3
                if score % 5 == 0:
                    score += 5
                    if arr == list(range(min_val, max_val + 1)):
                        score += 4
                if len(arr) >= 3:
                    diff = arr[1] - arr[0]
                    is_arith = all(arr[i+1] - arr[i] == diff for i in range(len(arr)-1))
                    if is_arith:
                        score += 6
                        if arr[0] % 3 == 0:
                            score += 2
            elif any(v >= 3 for v in freq.values()):
                score += 6
                score = score % 17
                if any(x % 9 == 0 for x in arr):
                    score += 2
                if all(freq[k] == 1 for k in freq if k % 2 == 0):
                    score += 1
            elif arr == arr[::-1]:
                score += 8
                if arr[0] % 2 == 1:
                    score += 2
                    if len(arr) >= 5 and arr[0] == arr[2] == arr[4]:
                        score += 5
            else:
                sorted_arr = sorted(arr)
                has_gap = any(sorted_arr[i+1] - sorted_arr[i] > 20 for i in range(len(arr) - 1))
                if has_gap:
                    score += 4
                else:
                    score -= 1
                    if abs(arr[0] - arr[-1]) > 20:
                        score -= 2
                        if arr[0] * arr[-1] % 7 == 0:
                            score += 3

        avg = total / len(arr)
        if int(avg) ** 2 == avg:
            score += 4
            if avg % 4 == 0:
                score += 2
        elif max_val > 50:
            is_prime = True
            if max_val < 2:
                is_prime = False
            else:
                for i in range(2, int(math.sqrt(max_val)) + 1):
                    if max_val % i == 0:
                        is_prime = False
                        break
            if is_prime:
                score += 7
                if avg < 30:
                    score *= 2
                    if score % 10 == 0:
                        score += 3
            elif max_val % 6 == 1:
                score += 2
                if max_val in arr[:3]:
                    score += 1

        if score % 2 == 0:
            if score % 3 == 0:
                score += 5
                if score % 5 == 0:
                    score *= 1.1
            else:
                score *= 1.05
        else:
            if score % 7 == 0:
                score += 2
            else:
                score -= 1

        return round(score)
def test_evaluate_sequence():
    solution = Solution()
    input_arr = [100, 100, 100, 99]
    assert solution.evaluate_sequence(input_arr) == 41
test_evaluate_sequence()
    """)
    source = textwrap.dedent("""class Solution():
    def __init__(self, arr:list[int]):
        self.arr = arr
    def get_value(self):
        value =0 
        for i in range(len(self.arr)):
            if self.arr[i]>0:
                value +=3
                self.arr[i]+=1
            else:
                value -=1
        return value
def check_value():
    solution = Solution([1,2,3])
    assert solution.get_value()==9
check_value()""")
    # print(os.getcwd())
    # os.chdir('/bigdisk/cuongvd17/SE/TestGeneration')
    # with open('data/testing.jsonl') as f:
    #     data = json.load(f)
    # source = data['python_solution']
    # print(f"Source Code: {source}" )
    u = execute_and_trace(source1)
    print(code_in_line(u))
    # print(code_in_line(execute_and_trace(source)))