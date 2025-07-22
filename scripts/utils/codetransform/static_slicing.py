import json
import ast
from utils.codetransform.utils1 import ExecutionOrderAnalyzer

""" --- ExecutionOrderAnalyzer Usage ---
analyzer = ExecutionOrderAnalyzer(source_code)
result = analyzer.analyze()

result: a dictionary represents line dependencies of code
"""

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


def static_slicing(source_code, target_line):
    analyzer = ExecutionOrderAnalyzer(source_code)
    line_dependencies = analyzer.analyze()

    def find_nodes_with_path_to_target(graph, target):
        """Find all nodes that have a path to the target node using reverse DFS"""
        # Create reverse graph
        reverse_graph = {}
        for node, neighbors in graph.items():
            for neighbor in neighbors:
                if neighbor not in reverse_graph:
                    reverse_graph[neighbor] = set()
                reverse_graph[neighbor].add(node)
        
        # DFS from target in reverse graph
        visited = set()
        stack = [target]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            if current in reverse_graph:
                for predecessor in reverse_graph[current]:
                    if predecessor not in visited:
                        stack.append(predecessor)
        
        return visited

    # Get initial reachable lines
    reachable_lines = find_nodes_with_path_to_target(line_dependencies, target_line)

    # Find all parent blocks needed
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


