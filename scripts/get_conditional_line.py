import ast
from typing import List, Set, Dict

class ControlFlowAnalyzer:
    def __init__(self):
        self.dependencies = {}  # line_number -> set of controlling lines
        
    def find_conditional_lines(self, code: str, target_line: int) -> List[int]:
        """
        Find all conditional lines that affect the target line.
        
        Args:
            code: Python source code as string
            target_line: Line number to analyze (1-based)
            
        Returns:
            List of line numbers that conditionally control the target line
        """
        try:
            tree = ast.parse(code)
            self._analyze_node(tree, set())
            return sorted(list(self.dependencies.get(target_line, set())))
        except SyntaxError as e:
            raise ValueError(f"Invalid Python code: {e}")
    
    def _analyze_node(self, node: ast.AST, controlling_conditions: Set[int]):
        """Recursively analyze AST nodes to build control flow dependencies."""
        
        # First, check if this node itself has a line number and record its dependencies
        if hasattr(node, 'lineno'):
            # Record dependencies for all nodes with line numbers
            if controlling_conditions:
                self.dependencies[node.lineno] = controlling_conditions.copy()
        
        # Handle different types of control flow statements
        if isinstance(node, ast.If):
            self._handle_if_statement(node, controlling_conditions)
        elif isinstance(node, ast.While):
            self._handle_while_statement(node, controlling_conditions)
        elif isinstance(node, ast.For):
            self._handle_for_statement(node, controlling_conditions)
        elif isinstance(node, ast.Try):
            self._handle_try_statement(node, controlling_conditions)
        elif isinstance(node, ast.With):
            self._handle_with_statement(node, controlling_conditions)
        elif isinstance(node, ast.Match):
            self._handle_match_statement(node, controlling_conditions)
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            self._handle_function_def(node, controlling_conditions)
        elif isinstance(node, ast.ClassDef):
            self._handle_class_def(node, controlling_conditions)
        else:
            # For other nodes, just process children with current conditions
            self._process_children(node, controlling_conditions)
    
    def _handle_if_statement(self, node: ast.If, controlling_conditions: Set[int]):
        """Handle if/elif/else statements."""
        condition_line = node.lineno
        new_conditions = controlling_conditions | {condition_line}
        
        # Process if body - statements in the if body are controlled by this if
        for stmt in node.body:
            self._analyze_node(stmt, new_conditions)
        
        # Process elif/else - collect all if/elif conditions for proper control flow
        all_if_conditions = controlling_conditions | {condition_line}
        self._handle_else_elif_chain(node.orelse, all_if_conditions)
    
    def _handle_else_elif_chain(self, orelse_nodes: List[ast.AST], all_if_conditions: Set[int]):
        """Handle the elif/else chain, accumulating all controlling conditions."""
        for child in orelse_nodes:
            if isinstance(child, ast.If):  # elif
                elif_line = child.lineno
                # elif body depends on all previous if/elif conditions plus this elif
                elif_conditions = all_if_conditions | {elif_line}
                
                # Process elif body
                for stmt in child.body:
                    self._analyze_node(stmt, elif_conditions)
                
                # Continue with the next elif/else, adding this elif to the chain
                next_conditions = all_if_conditions | {elif_line}
                self._handle_else_elif_chain(child.orelse, next_conditions)
            else:  # else body
                # else body depends on all if/elif conditions that came before
                self._analyze_node(child, all_if_conditions)
    
    def _handle_while_statement(self, node: ast.While, controlling_conditions: Set[int]):
        """Handle while loops."""
        condition_line = node.lineno
        new_conditions = controlling_conditions | {condition_line}
        
        # Process while body
        for stmt in node.body:
            self._analyze_node(stmt, new_conditions)
            
        # Process else clause (executed if loop completes normally)
        for stmt in node.orelse:
            self._analyze_node(stmt, controlling_conditions)
    
    def _handle_for_statement(self, node: ast.For, controlling_conditions: Set[int]):
        """Handle for loops."""
        condition_line = node.lineno
        new_conditions = controlling_conditions | {condition_line}
        
        # Process for body
        for stmt in node.body:
            self._analyze_node(stmt, new_conditions)
            
        # Process else clause
        for stmt in node.orelse:
            self._analyze_node(stmt, controlling_conditions)
    
    def _handle_try_statement(self, node: ast.Try, controlling_conditions: Set[int]):
        """Handle try/except/finally statements."""
        try_line = node.lineno
        new_conditions = controlling_conditions | {try_line}
        
        # Process try body
        for stmt in node.body:
            self._analyze_node(stmt, new_conditions)
        
        # Process except handlers
        for handler in node.handlers:
            handler_conditions = controlling_conditions | {handler.lineno}
            for stmt in handler.body:
                self._analyze_node(stmt, handler_conditions)
        
        # Process else clause (executed if no exception)
        for stmt in node.orelse:
            self._analyze_node(stmt, new_conditions)
            
        # Process finally clause
        for stmt in node.finalbody:
            # Treat finally block as controlled by the try statement context
            self._analyze_node(stmt, new_conditions)
    
    def _handle_match_statement(self, node: ast.Match, controlling_conditions: Set[int]):
        """Handle match-case statements (Python 3.10+)."""
        # Each case body is controlled by its case pattern (and optional guard)
        for case in node.cases:
            # match_case nodes may not have lineno; prefer pattern.lineno when available
            case_line = getattr(case.pattern, 'lineno', getattr(case, 'lineno', node.lineno))
            case_conditions = controlling_conditions | {case_line}
            if case.guard is not None and hasattr(case.guard, 'lineno'):
                case_conditions = case_conditions | {case.guard.lineno}
            for stmt in case.body:
                self._analyze_node(stmt, case_conditions)
    
    def _handle_with_statement(self, node: ast.With, controlling_conditions: Set[int]):
        """Handle with statements."""
        with_line = node.lineno
        new_conditions = controlling_conditions | {with_line}
        
        for stmt in node.body:
            self._analyze_node(stmt, new_conditions)
    
    def _handle_function_def(self, node: ast.FunctionDef, controlling_conditions: Set[int]):
        """Handle function definitions."""
        # Function body is not affected by parent conditions
        for stmt in node.body:
            self._analyze_node(stmt, set())
    
    def _handle_class_def(self, node: ast.ClassDef, controlling_conditions: Set[int]):
        """Handle class definitions."""
        # Class body is not affected by parent conditions
        for stmt in node.body:
            self._analyze_node(stmt, set())
    
    def _process_children(self, node: ast.AST, controlling_conditions: Set[int]):
        """Process all children of a node with given conditions."""
        for child in ast.iter_child_nodes(node):
            self._analyze_node(child, controlling_conditions)


def get_conditional_lines(code: str, target_line: int) -> List[int]:
    """
    Main function to find conditional lines affecting a target line.
    
    Args:
        code: Python source code as string
        target_line: Line number to analyze (1-based)
        
    Returns:
        List of line numbers that conditionally control the target line
    """
    analyzer = ControlFlowAnalyzer()
    return analyzer.find_conditional_lines(code, target_line)


def debug_dependencies(code: str) -> Dict[int, Set[int]]:
    """Debug function to see all dependencies."""
    analyzer = ControlFlowAnalyzer()
    tree = ast.parse(code)
    analyzer._analyze_node(tree, set())
    return analyzer.dependencies


# Example usage and test cases
if __name__ == "__main__":
    test_code1 = """if A:     # line 1
    if B:   # line 2
        statement_C  # line 3
    else:   # line 4
        statement_D  # line 5
"""
    
    print("Test case 1 - Normal if-else statement:")
    print("All dependencies:", debug_dependencies(test_code1))
    
    # Test with different execution scenarios
    print(f"Line 3 depends on: {get_conditional_lines(test_code1, 3)}")
    print(f"Line 5 depends on: {get_conditional_lines(test_code1, 5)}")
    
    # Test case 2: Complex nested structure
    test_code2 = """if condition1:      # line 1
    while condition2:  # line 2
        if condition3:   # line 3
            statement1    # line 4
        for i in range(10):  # line 5
            statement2    # line 6
            if condition4:  # line 7
                statement3  # line 8
                statement5  # line 9
    else:              # line 10
        statement4      # line 11
"""
    
    print("\nTest case 2: Complex nested structure")
    print("All dependencies:", debug_dependencies(test_code2))
    print(f"Line 4 depends on: {get_conditional_lines(test_code2, 4)}")   # [1, 2, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code2, 6)}")   # [1, 2, 5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code2, 8)}")   # [1, 2, 5, 7]
    print(f"Line 9 depends on: {get_conditional_lines(test_code2, 9)}") # [1]
    
    # Test case 3: Try-except
    test_code3 = """try:                # line 1
    statement1      # line 2
    if condition:   # line 3
        statement2  # line 4
except Exception1:   # line 5
    statement3      # line 6
except Exception2:   # line 7
    statement4      # line 8
except Exception3:   # line 9
    statement5      # line 10
finally:           # line 11
    statement6      # line 12
"""
    
    print("\nTest case 3: Try-except statement:")
    print("All dependencies:", debug_dependencies(test_code3))
    print(f"Line 2 depends on: {get_conditional_lines(test_code3, 2)}")  # [1]
    print(f"Line 4 depends on: {get_conditional_lines(test_code3, 4)}")  # [1, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code3, 6)}")  # [5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code3, 8)}")  # [5]
    print(f"Line 12 depends on: {get_conditional_lines(test_code3, 12)}")  # [5]

    # Test case 4: Complex nested if-else
    test_code4 = """if A:           # line 1
    if B:       # line 2
        if C:   # line 3
            stmt1  # line 4
        else:   # line 5
            stmt2  # line 6
    else:       # line 7
        stmt3   # line 8
else:           # line 9
    stmt4       # line 10
"""
    
    print("\nTest case 4: Nested if-else statement:")
    print("All dependencies:", debug_dependencies(test_code4))
    print(f"Line 3 depends on: {get_conditional_lines(test_code4, 3)}")   # [1, 2, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code4, 6)}")   # [1, 2, 3]
    print(f"Line 8 depends on: {get_conditional_lines(test_code4, 8)}")   # [1, 2]
    print(f"Line 10 depends on: {get_conditional_lines(test_code4, 10)}") # [1]
    
    # Test case 5: if-elif-else chain
    test_code5 = """if A:           # line 1
    stmt1       # line 2
elif B:         # line 3
    stmt2       # line 4
elif C:         # line 5
    stmt3       # line 6
else:           # line 7
    stmt4       # line 8
"""
    
    print("\nTest case 5: if-elif-else chain:")
    print("All dependencies:", debug_dependencies(test_code5))
    print(f"Line 2 depends on: {get_conditional_lines(test_code5, 2)}")   # [1]
    print(f"Line 4 depends on: {get_conditional_lines(test_code5, 4)}")   # [1, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code5, 6)}")   # [1, 3, 5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code5, 8)}")   # [1, 3, 5]

    #Test case 6: Match-case
    test_code6 = """match x:    # line 1
    case 1:        # line 2
        print("One") # line 3
    case 2:        # line 4
        print("Two") # line 5
    case 3:        # line 6
        print("Other") # line 7
"""
    print("\nTest case 6: Match-case statement:")
    print("All dependencies:", debug_dependencies(test_code6))
    print(f"Line 3 depends on: {get_conditional_lines(test_code6, 3)}")
    print(f"Line 5 depends on: {get_conditional_lines(test_code6, 5)}")
    print(f"Line 7 depends on: {get_conditional_lines(test_code6, 7)}")
    
    # Test case 7: Break, continue, and return statements
    test_code7 = """def process_data(items):    # line 1
    result = []              # line 2
    for item in items:       # line 3
        if item < 0:         # line 4
            continue         # line 5
        if item > 100:       # line 6
            break            # line 7
        result.append(item)  # line 8
    return result            # line 9
"""
    
    print("\nTest case 7: Break, Continue, Return statements:")
    print("All dependencies:", debug_dependencies(test_code7))
    print(f"Line 5 (continue) depends on: {get_conditional_lines(test_code7, 5)}")
    print(f"Line 7 (break) depends on: {get_conditional_lines(test_code7, 7)}")
