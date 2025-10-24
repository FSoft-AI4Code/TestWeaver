import json
import ast
from collections import defaultdict, deque
from typing import Dict, Set, List, Tuple, Optional
from utils.codetransform.utils1 import ExecutionOrderAnalyzer

""" --- ExecutionOrderAnalyzer Usage ---
analyzer = ExecutionOrderAnalyzer(source_code)
result = analyzer.analyze()

result: a dictionary represents line dependencies of code
"""

class DynamicSlicingAnalyzer:
    """Dynamic slicing analyzer implementing Agrawal and Horgan's Approach 2"""
    
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.split('\n')
        self.tree = ast.parse(source_code)
        
        # SDG components
        self.nodes = set()  # All statements (line numbers)
        self.edges = defaultdict(set)  # Dependencies between statements
        self.def_use_edges = defaultdict(set)  # def-use relations
        self.info_flow_edges = defaultdict(set)  # info-flow relations
        self.call_edges = defaultdict(set)  # Function call edges
        self.return_edges = defaultdict(set)  # Return edges
        
        # Execution tracking
        self.executed_nodes = set()  # Marked nodes (executed statements)
        self.executed_edges = set()  # Marked edges (executed dependencies)
        
        # Function mapping
        self.functions = {}  # function_name -> (start_line, end_line)
        self.function_calls = defaultdict(list)  # line -> [(func_name, call_line)]
        
        self._build_sdg()
    
    def _build_sdg(self):
        """Build System Dependence Graph (SDG) from static analysis"""
        # First, build static PDG for each function
        self._build_static_pdgs()
        
        # Then, link PDGs to create SDG
        self._link_pdgs_to_sdg()
    
    def _build_static_pdgs(self):
        """Build Program Dependence Graphs (PDGs) for each function"""
        # Use existing ExecutionOrderAnalyzer for static dependencies
        analyzer = ExecutionOrderAnalyzer(self.source_code)
        static_deps = analyzer.analyze()
        
        # Add all nodes and control/data dependencies
        for line, deps in static_deps.items():
            self.nodes.add(line)
            for dep in deps:
                self.nodes.add(dep)
                self.edges[dep].add(line)  # dep -> line (dependency direction)
        
        # Build function information
        self._extract_functions()
        
        # Add def-use and info-flow relations
        self._build_def_use_relations()
        self._build_info_flow_relations()
    
    def _extract_functions(self):
        """Extract function definitions and their boundaries"""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and hasattr(node, 'lineno'):
                start_line = node.lineno
                end_line = getattr(node, 'end_lineno', start_line)
                self.functions[node.name] = (start_line, end_line)
    
    def _build_def_use_relations(self):
        """Build def-use relations for variables"""
        # Track variable definitions and uses
        var_defs = {}  # var_name -> line_number
        var_uses = defaultdict(list)  # var_name -> [line_numbers]
        
        for node in ast.walk(self.tree):
            if hasattr(node, 'lineno'):
                line = node.lineno
                
                # Variable definitions (assignments)
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_defs[target.id] = line
                
                # Variable uses
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    var_uses[node.id].append(line)
        
        # Create def-use edges
        for var_name, def_line in var_defs.items():
            for use_line in var_uses[var_name]:
                if def_line != use_line:
                    self.def_use_edges[def_line].add(use_line)
    
    def _build_info_flow_relations(self):
        """Build info-flow relations for variables"""
        # Track variable definitions and their scopes
        var_defs = {}  # var_name -> (line_number, scope_level)
        var_uses = defaultdict(list)  # var_name -> [(line_number, scope_level)]
        
        # First pass: collect all variable definitions and uses with scope info
        scope_stack = []
        current_scope = 0
        
        for node in ast.walk(self.tree):
            if hasattr(node, 'lineno'):
                line = node.lineno
                
                # Track scope changes
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.If, ast.For, ast.While, ast.Try)):
                    scope_stack.append(current_scope)
                    current_scope += 1
                elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try)) and hasattr(node, 'orelse') and node.orelse:
                    # Handle else/elif/except/finally blocks
                    pass
                
                # Variable definitions (assignments)
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_defs[target.id] = (line, current_scope)
                
                # Variable uses
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    var_uses[node.id].append((line, current_scope))
        
        # Second pass: create info-flow edges based on scope and control flow
        for var_name, (def_line, def_scope) in var_defs.items():
            for use_line, use_scope in var_uses[var_name]:
                if def_line != use_line and use_scope >= def_scope:
                    # Check if there's a control flow path from def to use
                    if self._has_control_flow_path(def_line, use_line):
                        self.info_flow_edges[def_line].add(use_line)
    
    def _has_control_flow_path(self, from_line, to_line):
        """Check if there's a control flow path from one line to another"""
        # Simplified check: if to_line comes after from_line in execution order
        # and they're in the same or nested scope
        return to_line > from_line
    
    def _link_pdgs_to_sdg(self):
        """Link individual PDGs to create System Dependence Graph"""
        # Add call and return edges
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and hasattr(node, 'lineno'):
                call_line = node.lineno
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name in self.functions:
                        func_start, func_end = self.functions[func_name]
                        # Add call edge: call site -> function entry
                        self.call_edges[call_line].add(func_start)
                        # Add return edge: function exit -> call site
                        self.return_edges[func_end].add(call_line)
                        self.function_calls[call_line].append((func_name, call_line))
                
                # Handle method calls
                elif isinstance(node.func, ast.Attribute):
                    # For method calls, we need to find the class and method
                    if isinstance(node.func.value, ast.Name):
                        class_name = node.func.value.id
                        method_name = node.func.attr
                        method_full_name = f"{class_name}.{method_name}"
                        
                        # Look for the method in our function mapping
                        for full_method_name, (start_line, end_line) in self.functions.items():
                            if full_method_name == method_full_name:
                                self.call_edges[call_line].add(start_line)
                                self.return_edges[end_line].add(call_line)
                                self.function_calls[call_line].append((method_full_name, call_line))
                                break
    
    def mark_executed_nodes_and_edges(self, executed_lines: List[int]):
        """Mark nodes and edges as executed based on test execution data"""
        executed_set = set(executed_lines)
        
        # Mark executed nodes
        for line in executed_lines:
            if line in self.nodes:
                self.executed_nodes.add(line)
        
        # Mark executed edges (dependencies that were actually executed)
        for source_line in executed_set:
            if source_line in self.edges:
                for target_line in self.edges[source_line]:
                    if target_line in executed_set:
                        self.executed_edges.add((source_line, target_line))
        
        # Mark def-use edges that were executed
        for source_line in executed_set:
            if source_line in self.def_use_edges:
                for target_line in self.def_use_edges[source_line]:
                    if target_line in executed_set:
                        self.executed_edges.add((source_line, target_line))
        
        # Mark info-flow edges that were executed
        for source_line in executed_set:
            if source_line in self.info_flow_edges:
                for target_line in self.info_flow_edges[source_line]:
                    if target_line in executed_set:
                        self.executed_edges.add((source_line, target_line))
        
        # Mark call edges that were executed
        for call_line in executed_set:
            if call_line in self.call_edges:
                for func_start in self.call_edges[call_line]:
                    if func_start in executed_set:
                        self.executed_edges.add((call_line, func_start))
        
        # Mark return edges that were executed
        for func_end in executed_set:
            if func_end in self.return_edges:
                for return_line in self.return_edges[func_end]:
                    if return_line in executed_set:
                        self.executed_edges.add((func_end, return_line))
    
    def dynamic_backward_slice(self, target_line: int) -> Set[int]:
        """Perform dynamic backward slicing from target line"""
        if target_line not in self.executed_nodes:
            return set()
        
        # BFS from target line, following only executed edges
        visited = set()
        queue = deque([target_line])
        slice_nodes = set()
        
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            
            visited.add(current)
            slice_nodes.add(current)
            
            # Follow executed edges backward
            for source_line in self.nodes:
                if (source_line, current) in self.executed_edges:
                    if source_line not in visited:
                        queue.append(source_line)
        
        return slice_nodes

def find_all_parent_blocks(source_code, reachable_lines):
    """Find all parent block statements needed to keep reachable lines valid"""
    lines = source_code.split('\n')
    lines_to_keep = set(reachable_lines)
    
    # Build indentation structure to find parent blocks
    indentation_stack = []  # Stack of (line_number, indent_level, is_block_stmt)
    
    for line_num, line in enumerate(lines, start=1):
        if not line.strip():  # Skip empty lines
            continue
            
        current_indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        is_block_statement = stripped.endswith(':') and not stripped.startswith('#')
        
        # Pop from stack if current line has less or equal indentation
        while (indentation_stack and 
                indentation_stack[-1][1] >= current_indent and
                not (indentation_stack[-1][1] == current_indent and is_block_statement)):
            indentation_stack.pop()
        
        # If current line is reachable, add all its parents to lines_to_keep
        if line_num in reachable_lines:
            for parent_line, parent_indent, parent_is_block in indentation_stack:
                if parent_is_block:
                    lines_to_keep.add(parent_line)
        
        # Add current line to stack if it's a block statement
        if is_block_statement:
            indentation_stack.append((line_num, current_indent, True))
        else:
            # Add non-block statements too for context
            indentation_stack.append((line_num, current_indent, False))
    
    return lines_to_keep

def find_required_structural_lines(source_code, lines_to_keep):
    """Find additional structural lines needed for code validity"""
    lines = source_code.split('\n')
    additional_lines = set()
    
    # Parse AST to understand structure
    try:
        tree = ast.parse(source_code)
        
        # Find all block statements and their relationships
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and hasattr(node, 'lineno'):
                if_line = node.lineno
                
                # Check if any line in if body is kept
                if_body_kept = any(hasattr(stmt, 'lineno') and stmt.lineno in lines_to_keep 
                                for stmt in node.body)
                
                # Check if any line in else body is kept
                else_body_kept = False
                else_line = None
                if node.orelse:
                    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                        # This is elif
                        elif_node = node.orelse[0]
                        if hasattr(elif_node, 'lineno'):
                            else_line = elif_node.lineno
                            else_body_kept = any(hasattr(stmt, 'lineno') and stmt.lineno in lines_to_keep 
                                            for stmt in elif_node.body)
                    else:
                        # This is else
                        for stmt in node.orelse:
                            if hasattr(stmt, 'lineno'):
                                if stmt.lineno in lines_to_keep:
                                    else_body_kept = True
                                if else_line is None:
                                    # Find the else line by looking at source
                                    for i, line in enumerate(lines, 1):
                                        if (i > if_line and 
                                            line.strip().startswith('else:') and
                                            i < stmt.lineno):
                                            else_line = i
                                            break
                
                # If if body is kept, keep the if statement
                if if_body_kept:
                    additional_lines.add(if_line)
                
                # If else body is kept, keep the else statement
                if else_body_kept and else_line:
                    additional_lines.add(else_line)
                    additional_lines.add(if_line)  # Also need the if
            
            # Handle try-except-finally blocks
            elif isinstance(node, ast.Try) and hasattr(node, 'lineno'):
                try_line = node.lineno
                
                # Check try body
                try_body_kept = any(hasattr(stmt, 'lineno') and stmt.lineno in lines_to_keep 
                                for stmt in node.body)
                
                # Check handlers
                handlers_kept = []
                for handler in node.handlers:
                    if hasattr(handler, 'lineno'):
                        handler_kept = any(hasattr(stmt, 'lineno') and stmt.lineno in lines_to_keep 
                                        for stmt in handler.body)
                        if handler_kept:
                            handlers_kept.append(handler.lineno)
                
                # Check finally
                finally_kept = False
                finally_line = None
                if node.finalbody:
                    finally_kept = any(hasattr(stmt, 'lineno') and stmt.lineno in lines_to_keep 
                                    for stmt in node.finalbody)
                    if finally_kept:
                        # Find finally line
                        for i, line in enumerate(lines, 1):
                            if (i > try_line and 
                                line.strip().startswith('finally:')):
                                finally_line = i
                                break
                
                # Add necessary structural lines
                if try_body_kept or handlers_kept or finally_kept:
                    additional_lines.add(try_line)
                
                for handler_line in handlers_kept:
                    additional_lines.add(handler_line)
                
                if finally_kept and finally_line:
                    additional_lines.add(finally_line)
    
    except SyntaxError:
        # If AST parsing fails, fall back to simpler heuristics
        pass
    
    return additional_lines


def dynamic_slicing(source_code, target_line, result_execute):
    """
    Dynamic slicing implementation based on Agrawal and Horgan's Approach 2.
    
    Args:
        source_code: Source code to slice
        target_line: Target line to slice from
        result_execute: List of test execution data in format:
            [{"test": "", "executed_lines": [1,2,3]}, ...]
    
    Returns:
        Tuple of (filtered_code, orig_num_lines, filter_num_lines, reachable_lines)
    """
    # Initialize dynamic slicing analyzer
    analyzer = DynamicSlicingAnalyzer(source_code)
    
    # Phase 1: Mark executed nodes and edges based on test execution data
    # Combine all executed lines from all test cases
    all_executed_lines = set()
    for test_data in result_execute:
        if 'executed_lines' in test_data:
            all_executed_lines.update(test_data['executed_lines'])
    
    # Mark executed nodes and edges
    analyzer.mark_executed_nodes_and_edges(list(all_executed_lines))
    
    # Phase 2: Perform dynamic backward slicing
    # Only traverse along marked (executed) nodes and edges
    reachable_lines = analyzer.dynamic_backward_slice(target_line)
    
    # Find all parent blocks needed for structural validity
    lines_to_keep = find_all_parent_blocks(source_code, reachable_lines)
    
    # Find additional structural lines
    additional_structural = find_required_structural_lines(source_code, lines_to_keep)
    lines_to_keep.update(additional_structural)
    
    # Sort for processing
    lines_to_keep = sorted(lines_to_keep)

    # Split source code into lines
    lines = source_code.split('\n')
    orig_num_lines = len(lines)
    result_lines = []

    # Implementation to get result_lines
    kept_set = set(lines_to_keep)
    
    # Process each line
    for i, line in enumerate(lines, start=1):
        if i in kept_set:
            result_lines.append(line)
            
            # Check if this is a block statement that needs a body
            stripped = line.lstrip()
            indent_level = len(line) - len(stripped)
            
            is_block_statement = (
                stripped.rstrip().endswith(':') and 
                not stripped.startswith('#') and 
                stripped.strip() != ':'
            )
            
            if is_block_statement:
                # Check if the next kept line has proper body indentation
                expected_body_indent = indent_level + 4
                has_proper_body = False
                
                # Look ahead in kept lines to see if there's a proper body
                for j in range(i + 1, len(lines) + 1):
                    if j in kept_set:
                        next_line = lines[j - 1]
                        next_stripped = next_line.lstrip()
                        next_indent = len(next_line) - len(next_stripped)
                        
                        if next_stripped and next_indent >= expected_body_indent:
                            has_proper_body = True
                            break
                        elif next_stripped and next_indent <= indent_level:
                            # Next line is at same or lower indentation, no body found
                            break
                
                # If no proper body found, add pass statement
                if not has_proper_body:
                    result_lines.append(' ' * expected_body_indent + 'pass')

    # Clean up any remaining placeholders needed
    filter_num_lines = len(result_lines)
    filtered_code = '\n'.join(result_lines)
    # print("Filtered code:")
    # print(filtered_code)
    return filtered_code, orig_num_lines, filter_num_lines, reachable_lines

