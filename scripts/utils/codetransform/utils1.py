import re
import ast
import textwrap
import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Any, Set, Tuple

import ast
from collections import defaultdict
from typing import Dict, Set, List, Optional

class ExecutionOrderAnalyzer:
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.strip().split('\n')
        self.tree = ast.parse(source_code)
        self.execution_order: Dict[int, Set[int]] = defaultdict(set)
        self.functions: Dict[str, int] = {}
        self.classes: Dict[str, int] = {}
        self.methods: Dict[str, int] = {}
        self.meaningless_lines = self._identify_meaningless_lines(source_code)
        self._build_function_and_class_start_lines()
        
    def _identify_meaningless_lines(self, source_code: str) -> Set[int]:
        """Identify all meaningless lines that should be ignored in dependency analysis"""
        lines = source_code.splitlines()
        meaningless_lines = set()

        # 1. Empty lines or lines with only whitespace
        # 2. Comment-only lines (lines that start with # after stripping whitespace)
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                meaningless_lines.add(i)

        # 3. Docstrings (triple-quoted strings as expression statements)
        # 4. Pass statements
        # 5. Ellipsis (...) statements
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Expr):
                # Docstrings: String literals as expression statements
                if (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)) or \
                   (hasattr(ast, 'Str') and isinstance(node.value, ast.Str)):
                    if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                        for l in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                            meaningless_lines.add(l)
                    elif hasattr(node, 'lineno'):
                        meaningless_lines.add(node.lineno)
                
                # Ellipsis (...) statements
                elif isinstance(node.value, ast.Constant) and node.value.value is ...:
                    if hasattr(node, 'lineno'):
                        meaningless_lines.add(node.lineno)
                elif hasattr(ast, 'Ellipsis') and isinstance(node.value, ast.Ellipsis):
                    if hasattr(node, 'lineno'):
                        meaningless_lines.add(node.lineno)
            
            # Pass statements
            elif isinstance(node, ast.Pass):
                if hasattr(node, 'lineno'):
                    meaningless_lines.add(node.lineno)

        return meaningless_lines

    def _build_function_and_class_start_lines(self):
        """Build mapping of functions/classes to their first executable line"""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and hasattr(node, 'lineno'):
                # Find first meaningful line in function body
                first_meaningful_line = self._find_first_meaningful_line(node.body, node.lineno)
                self.functions[node.name] = first_meaningful_line
                
            elif isinstance(node, ast.ClassDef) and hasattr(node, 'lineno'):
                self.classes[node.name] = node.lineno
                
                # Process methods in class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and hasattr(item, 'lineno'):
                        method_full_name = f"{node.name}.{item.name}"
                        first_meaningful_line = self._find_first_meaningful_line(item.body, item.lineno)
                        self.methods[method_full_name] = first_meaningful_line

    def _find_first_meaningful_line(self, body: List[ast.stmt], fallback_line: int) -> int:
        """Find the first meaningful (non-ignored) line in a statement body"""
        for stmt in body:
            if hasattr(stmt, 'lineno') and stmt.lineno not in self.meaningless_lines:
                return stmt.lineno
        return fallback_line

    def analyze(self) -> Dict[int, Set[int]]:
        """Analyze execution order dependencies, ignoring meaningless lines"""
        self._process_block(self.tree.body, set())
        # Filter out any meaningless lines from the final result
        filtered_result = {}
        for line, deps in self.execution_order.items():
            if line not in self.meaningless_lines:
                meaningful_deps = {dep for dep in deps if dep not in self.meaningless_lines}
                if meaningful_deps:
                    filtered_result[line] = meaningful_deps
        return filtered_result

    def _process_block(self, statements: List[ast.stmt], prev_lines: Set[int]) -> Set[int]:
        current_prev = prev_lines.copy()
        for i, stmt in enumerate(statements):
            next_stmt_line = self._find_next_meaningful_line(statements, i)
            current_prev = self._process_statement(stmt, current_prev, next_stmt_line)
        return current_prev

    def _find_next_meaningful_line(self, statements: List[ast.stmt], current_index: int) -> Optional[int]:
        """Find the next meaningful line after current statement"""
        for j in range(current_index + 1, len(statements)):
            stmt = statements[j]
            if hasattr(stmt, 'lineno') and stmt.lineno not in self.meaningless_lines:
                return stmt.lineno
        return None

    def _process_statement(self, node: ast.stmt, prev_lines: Set[int], next_stmt_line: Optional[int]) -> Set[int]:
        if not hasattr(node, 'lineno'):
            return prev_lines
        
        current_line = node.lineno

        # Skip meaningless lines entirely
        if current_line in self.meaningless_lines:
            return prev_lines
        
        # Only create dependencies between meaningful lines
        meaningful_prev_lines = {line for line in prev_lines if line not in self.meaningless_lines}
        for prev_line in meaningful_prev_lines:
            if prev_line != current_line:
                self.execution_order[prev_line].add(current_line)
        
        if isinstance(node, ast.FunctionDef):
            if node.body:
                self._process_block(node.body, {current_line})
            return {current_line}
        
        elif isinstance(node, ast.ClassDef):
            if node.body:
                self._process_block(node.body, {current_line})
            return {current_line}
        
        elif isinstance(node, ast.If):
            if_end_lines = self._process_block(node.body, {current_line})
            else_end_lines = set()
            if node.orelse:
                if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                    else_end_lines = self._process_statement(node.orelse[0], {current_line}, next_stmt_line)
                else:
                    else_end_lines = self._process_block(node.orelse, {current_line})
            else:
                else_end_lines = {current_line}
            
            if next_stmt_line and next_stmt_line != current_line:
                self.execution_order[current_line].add(next_stmt_line)
            
            return if_end_lines.union(else_end_lines)
        
        elif isinstance(node, (ast.For, ast.While)):
            loop_line = current_line
            body_end_lines = self._process_block(node.body, {loop_line})
            
            # Loop back connections
            meaningful_end_lines = {line for line in body_end_lines if line not in self.meaningless_lines}
            for end_line in meaningful_end_lines:
                self.execution_order[end_line].add(loop_line)
            
            if hasattr(node, 'orelse') and node.orelse:
                self._process_block(node.orelse, {loop_line})
            
            if next_stmt_line and next_stmt_line != current_line:
                self.execution_order[loop_line].add(next_stmt_line)
            return {loop_line}
        
        elif isinstance(node, ast.Try):
            try_line = current_line
            try_end_lines = self._process_block(node.body, {try_line})
            
            # Exception handlers
            handler_end_lines = set()
            for handler in node.handlers:
                if hasattr(handler, 'lineno') and handler.lineno not in self.meaningless_lines:
                    handler_line = handler.lineno
                    # Exception can jump from any meaningful line in try block to handler
                    for stmt in node.body:
                        if hasattr(stmt, 'lineno') and stmt.lineno not in self.meaningless_lines:
                            self.execution_order[stmt.lineno].add(handler_line)
                    
                    handler_end = self._process_block(handler.body, {handler_line})
                    handler_end_lines.update(handler_end)
            
            # Finally block
            finally_end_lines = set()
            if node.finalbody:
                # Find first meaningful line in finally block
                finally_line = None
                for stmt in node.finalbody:
                    if hasattr(stmt, 'lineno') and stmt.lineno not in self.meaningless_lines:
                        finally_line = stmt.lineno
                        break
                
                if finally_line:
                    # Connect try and handler end lines to finally
                    meaningful_end_lines = {line for line in try_end_lines.union(handler_end_lines) 
                                          if line not in self.meaningless_lines}
                    for end_line in meaningful_end_lines:
                        self.execution_order[end_line].add(finally_line)
                    
                    finally_end_lines = self._process_block(node.finalbody, {finally_line})
            
            all_end_lines = try_end_lines.union(handler_end_lines).union(finally_end_lines)
            return all_end_lines if all_end_lines else {try_line}
        
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            self._handle_function_call(node.value, current_line)
            if next_stmt_line and next_stmt_line != current_line:
                self.execution_order[current_line].add(next_stmt_line)
            return {current_line}
        
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            self._handle_function_call(node.value, current_line)
            if next_stmt_line and next_stmt_line != current_line:
                self.execution_order[current_line].add(next_stmt_line)
            return {current_line}

        else:
            if next_stmt_line and next_stmt_line != current_line:
                self.execution_order[current_line].add(next_stmt_line)
            return {current_line}

    def _handle_function_call(self, call_node: ast.Call, current_line: int):
        """Handle function and method call dependencies"""
        if isinstance(call_node.func, ast.Name):
            func_name = call_node.func.id
            if func_name in self.classes:
                # Class instantiation - connect to __init__
                init_method_name = f"{func_name}.__init__"
                if init_method_name in self.methods:
                    init_first_line = self.methods[init_method_name]
                    if current_line != init_first_line:
                        self.execution_order[current_line].add(init_first_line)
            elif func_name in self.functions:
                # Function call
                first_exec_line = self.functions[func_name]
                if current_line != first_exec_line:
                    self.execution_order[current_line].add(first_exec_line)
        elif isinstance(call_node.func, ast.Attribute):
            # Method call
            attr = call_node.func
            if isinstance(attr.value, ast.Name):
                method_name = attr.attr
                for full_method_name, line_num in self.methods.items():
                    if full_method_name.endswith(f".{method_name}"):
                        self.execution_order[current_line].add(line_num)
                        break

# Comprehensive test
def test_meaningless_lines():
    source_code = """\
import random
from typing import List


class ArrayGenerator:
    '''Utility to create random integer arrays.'''

    @staticmethod
    def generate(size: int, low: int = 0, high: int = 100) -> List[int]:
        return [random.randint(low, high) for _ in range(size)]


class Sorter:
    '''Abstract base sorter.'''

    def sort(self, data: List[int]) -> List[int]:
        '''Return a sorted copy of *data* (to be overridden).'''
        raise NotImplementedError("Subclasses must override sort()")

    def _is_sorted(self, data: List[int]) -> bool:
        '''Helper shared by all subclasses.'''
        return all(a <= b for a, b in zip(data, data[1:]))


class QuickSorter(Sorter):
    '''Concrete sorter implementing QuickSort (overrides Sorter.sort).'''

    def sort(self, data: List[int]) -> List[int]:
        # ---- Nested helper functions ----
        def partition(arr: List[int], lo: int, hi: int) -> int:
            pivot = arr[hi]
            i = lo - 1
            for j in range(lo, hi):
                if arr[j] <= pivot:
                    i += 1
                    arr[i], arr[j] = arr[j], arr[i]
            arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
            return i + 1

        def quicksort(arr: List[int], lo: int, hi: int) -> None:
            if lo < hi:
                p = partition(arr, lo, hi)
                quicksort(arr, lo, p - 1)
                quicksort(arr, p + 1, hi)

        # ---- Make a copy so we do not mutate the caller’s list ----
        arr_copy = data[:]
        quicksort(arr_copy, 0, len(arr_copy) - 1)
        return arr_copy


class MergeSorter(Sorter):
    '''Another concrete sorter (merge sort) to show multiple subclasses.'''

    def sort(self, data: List[int]) -> List[int]:
        def mergesort(arr: List[int]) -> List[int]:
            if len(arr) <= 1:
                return arr
            mid = len(arr) // 2
            left = mergesort(arr[:mid])
            right = mergesort(arr[mid:])
            return merge(left, right)

        def merge(left: List[int], right: List[int]) -> List[int]:
            merged = []
            i = j = 0
            while i < len(left) and j < len(right):
                if left[i] <= right[j]:
                    merged.append(left[i])
                    i += 1
                else:
                    merged.append(right[j])
                    j += 1
            merged.extend(left[i:])
            merged.extend(right[j:])
            return merged

        return mergesort(data[:])


if __name__ == "__main__":
    SIZE = 15
    array = ArrayGenerator.generate(SIZE, 0, 50)
    print("Original array :", array)

    quick_sorted = QuickSorter().sort(array)
    merge_sorted = MergeSorter().sort(array)

    print("QuickSorter result:", quick_sorted)
    print("MergeSorter result:", merge_sorted)
    print("Both equal?       :", quick_sorted == merge_sorted)
"""

    analyzer = ExecutionOrderAnalyzer(source_code)
    result = analyzer.analyze()
    
# test_meaningless_lines()



def change_function_name(code: str, new_name: str) -> str:
    """
    Change the name of the first function definition in the given code.
    
    Args:
        code: Source code string
        new_name: New function name
        
    Returns:
        Modified code string, or original code if parsing fails
    """
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name != new_name:
                    node.name = new_name
                break
        
        return ast.unparse(tree)
    except Exception:
        return code


def reformat_case_byrules(testcase: str, func_name: str, lang: str = 'python') -> str:
    """
    Reformat a test case by removing extra indentation and changing function name.
    
    Args:
        testcase: Test case code string
        func_name: Function name to use
        lang: Programming language (default: 'python')
        
    Returns:
        Reformatted test case string
    """
    # Remove extra indentation
    if testcase.startswith(' '):
        testcase = textwrap.dedent(testcase)
    
    lines = testcase.split('\n')
    
    # Remove incomplete last line for Python
    if lang == 'python' and lines:
        last_line = textwrap.dedent(lines[-1])
        try:
            compile(last_line, '<string>', 'exec')
        except SyntaxError:
            lines = lines[:-1]
    
    testcase = '\n'.join(lines)
    return change_function_name(testcase, func_name)


def remove_extra(testcase: str, func_name: str, lang: str = 'python') -> str:
    """
    Remove extra content before and after the test method.
    Keep only content between 'def test' and 'solution.{func_name}'.
    
    Args:
        testcase: Test case code string
        func_name: Function name to look for
        lang: Programming language (default: 'python')
        
    Returns:
        Cleaned test case string
    """
    lines = testcase.split('\n')
    
    # Find test function start
    func_startline = 0
    for i, line in enumerate(lines):
        if 'def test' in line:
            func_startline = i
            break
    
    # Find test function end
    test_endline = len(lines)
    solution_call = f'solution.{func_name}'
    for i, line in enumerate(lines):
        if solution_call in line:
            test_endline = i + 1
            break
    
    return '\n'.join(lines[func_startline:test_endline])


def reformat_line(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reformat test data by processing all test cases for each function.
    
    Args:
        data: List of dictionaries containing code and test information
        
    Returns:
        Formatted data with processed test cases
    """
    formatted_data = []
    
    for entry in data:
        code = entry['code']
        func_name = entry['func_name']
        test_funcname = f'test_{func_name}'
        tests = entry['tests']
        
        # Process tests for each line number
        for lineno in tests:
            reformatted_testcase = []
            for testcase in tests[lineno]:
                cleaned_testcase = remove_extra(testcase, func_name)
                formatted_testcase = reformat_case_byrules(cleaned_testcase, test_funcname, 'python')
                reformatted_testcase.append(formatted_testcase)
            
            tests[lineno] = reformatted_testcase
        
        entry['tests'] = tests
        formatted_data.append(entry)
    
    return formatted_data


def add_lineno(code: str) -> str:
    """
    Add line numbers to code.
    
    Args:
        code: Source code string
        
    Returns:
        Code string with line numbers prepended
    """
    lines = code.split('\n')
    numbered_lines = [f'{i+1}. {line}' for i, line in enumerate(lines)]
    return '\n'.join(numbered_lines)