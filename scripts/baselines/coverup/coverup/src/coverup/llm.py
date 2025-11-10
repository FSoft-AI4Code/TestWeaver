import typing as T
import openai
import logging
import asyncio
import warnings
import textwrap
import json
import traceback
from aiolimiter import AsyncLimiter

with warnings.catch_warnings():
    # ignore pydantic warnings https://github.com/BerriAI/litellm/issues/2832
    warnings.simplefilter('ignore')
    import litellm # type: ignore


# Turn off most logging
litellm.set_verbose = False
litellm.suppress_debug_info = True
logging.getLogger().setLevel(logging.ERROR)

# Ignore unavailable parameters
litellm.drop_params=True


# Tier 5 rate limits for models; tuples indicate limit and interval in seconds
# Extracted from https://platform.openai.com/account/limits on 8/30/2024
MODEL_RATE_LIMITS = {
    'gpt-3.5-turbo': {
        'token': (50_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-3.5-turbo-0125': {
        'token': (50_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-3.5-turbo-1106': {
        'token': (50_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-3.5-turbo-16k': {
        'token': (50_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-3.5-turbo-instruct': {
        'token': (90_000, 60), 'request': (3_500, 60)
    },
    'gpt-3.5-turbo-instruct-0914': {
        'token': (90_000, 60), 'request': (3_500, 60)
    },
    'gpt-4': {
        'token': (1_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-0314': {
        'token': (1_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-0613': {
        'token': (1_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-32k-0314': {
        'token': (150_000, 60), 'request': (1_000, 60)
    },
    'gpt-4-turbo': {
        'token': (2_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-turbo-2024-04-09': {
        'token': (2_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-turbo-preview': {
        'token': (2_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-0125-preview': {
        'token': (2_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4-1106-preview': {
        'token': (2_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4o': {
        'token': (30_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4o-2024-05-13': {
        'token': (30_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4o-2024-08-06': {
        'token': (30_000_000, 60), 'request': (10_000, 60)
    },
    'gpt-4o-mini': {
        'token': (150_000_000, 60), 'request': (30_000, 60)
    },
    'gpt-4o-mini-2024-07-18': {
        'token': (150_000_000, 60), 'request': (30_000, 60)
    }
}


def token_rate_limit_for_model(model_name: str) -> T.Tuple[int, int]|None:
    if model_name.startswith('openai/'):
        model_name = model_name[7:]

    # Skip rate limiting for DeepSeek models
    if model_name == "deepseek-v3-0324" or "deepseek" in model_name.lower():
        return None  # No rate limiting for DeepSeek

    if (model_limits := MODEL_RATE_LIMITS.get(model_name)):
        limit = model_limits.get('token')

        try:
            import tiktoken
            tiktoken.encoding_for_model(model_name)
        except KeyError:
            warnings.warn(f"Unable to get encoding for {model_name}; will ignore rate limit")
            return None

        return limit

    return None


def compute_cost(usage: dict, model_name: str) -> float|None:
    from math import ceil

    if model_name.startswith('openai/'):
        model_name = model_name[7:]
    
    # Skip cost calculation for DeepSeek models
    if model_name == "deepseek-v3-0324" or "deepseek" in model_name.lower():
        return None  # No cost tracking for DeepSeek

    if 'prompt_tokens' in usage and 'completion_tokens' in usage:
        if (cost := litellm.model_cost.get(model_name)):
            return usage['prompt_tokens'] * cost['input_cost_per_token'] +\
                   usage['completion_tokens'] * cost['output_cost_per_token']

    return None


_token_encoding_cache: dict[str, T.Any] = dict()
def count_tokens(model_name: str, completion: dict):
    """Counts the number of tokens in a chat completion request."""
    import tiktoken

    if not (encoding := _token_encoding_cache.get(model_name)):
        model = model_name
        if model_name.startswith('openai/'):
            model = model_name[7:]
        # Handle custom deepseek model by using gpt-4 encoding as fallback
        elif model_name == "deepseek-v3-0324":
            model = "gpt-4"

        try:
            encoding = _token_encoding_cache[model_name] = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to gpt-4 encoding for unknown models
            encoding = _token_encoding_cache[model_name] = tiktoken.encoding_for_model("gpt-4")

    count = 0
    for m in completion['messages']:
        count += len(encoding.encode(m['content']))

    return count


class ChatterError(Exception):
    pass


class Chatter:
    """Chats with an LLM."""

    def __init__(self, model: str) -> None:
        Chatter._validate_model(model)

        self._model = model
        self._model_temperature: float|None = None
        self._max_backoff = 64 # seconds
        self.token_rate_limit: AsyncLimiter|None
        self.set_token_rate_limit(token_rate_limit_for_model(model))
        self._add_cost = lambda cost: None
        self._log_msg = lambda ctx, msg: None
        self._log_json = lambda ctx, j: None
        self._signal_retry = lambda: None
        self._functions: dict[str, dict[str, T.Any]] = dict()
        self._max_func_calls_per_chat = 50


    @staticmethod
    def _validate_model(model) -> None:
        # Special case for DeepSeek models served through user's API endpoint
        if "deepseek" in model.lower():
            import os
            if not os.getenv('coverup') or not os.getenv('ANTHROPIC_BASE_URL'):
                raise ChatterError(textwrap.dedent(f"""\
                    For {model} model, you need to set:
                        export coverup=<your-api-key>
                        export ANTHROPIC_BASE_URL=<your-base-url>"""
                ))
            return  # Skip litellm validation for DeepSeek models
            
        try:
            _, provider, _, _ = litellm.get_llm_provider(model)
        except litellm.exceptions.BadRequestError:
            raise ChatterError(textwrap.dedent("""\
                Unknown or unsupported model.
                Please see https://docs.litellm.ai/docs/providers for supported models."""
            ))

        result = litellm.validate_environment(model)
        if result['missing_keys']:
            if provider == 'openai':
                raise ChatterError(textwrap.dedent("""\
                    You need an OpenAI key to use {model}.
                    
                    You can get a key here: https://platform.openai.com/api-keys
                    Set the environment variable OPENAI_API_KEY to your key value
                        export OPENAI_API_KEY=<your key>"""
                ))
            elif provider == 'bedrock':
                raise ChatterError(textwrap.dedent("""\
                    To use Bedrock, you need an AWS account. Set the following environment variables:
                       export AWS_ACCESS_KEY_ID=<your key id>
                       export AWS_SECRET_ACCESS_KEY=<your secret key>
                       export AWS_REGION_NAME=us-west-2

                    You also need to request access to Claude:
                       https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html#manage-model-access"""
                ))
            else:
                raise ChatterError(textwrap.dedent(f"""\
                    You need a key (or keys) from {provider} to use {model}.
                    Set the following environment variables:
                        {', '.join(result['missing_keys'])}"""
                ))


    def set_model_temperature(self, temperature: T.Optional[float]) -> None:
        self._model_temperature = temperature


    def set_token_rate_limit(self, limit: T.Union[T.Tuple[int, int], None]) -> None:
        if limit:
            self.token_rate_limit = AsyncLimiter(*limit)
        else:
            self.token_rate_limit = None


    def set_max_backoff(self, max_backoff: int) -> None:
        self._max_backoff = max_backoff


    def set_add_cost(self, add_cost: T.Callable) -> None:
        """Sets up a callback to indicate additional costs."""
        self._add_cost = add_cost


    def set_log_msg(self, log_msg: T.Callable[[str, str], None]) -> None:
        """Sets up a callback to write a message to the log."""
        self._log_msg = log_msg


    def set_log_json(self, log_json: T.Callable[[str, dict], None]) -> None:
        """Sets up a callback to write a json exchange to the log."""
        self._log_json = log_json


    def set_signal_retry(self, signal_retry: T.Callable) -> None:
        """Sets up a callback to indicate a retry."""
        self._signal_retry = signal_retry


    def add_function(self, function: T.Callable) -> None:
        """Makes a function availabe to the LLM."""
        # Special handling for DeepSeek models - assume they support function calling
        if "deepseek" not in self._model.lower() and not litellm.supports_function_calling(self._model):
            raise ChatterError(f"The {self._model} model does not support function calling.")

        try:
            schema = json.loads(getattr(function, "__doc__", ""))
            if 'name' not in schema:
                raise ChatterError("Name missing from function {function} schema.")
        except json.decoder.JSONDecodeError as e:
            raise ChatterError(f"Invalid JSON in function docstring: {e}")

        assert schema['name'] not in self._functions, "Duplicated function name {schema['name']}"
        self._functions[schema['name']] = {"function": function, "schema": schema}


    def _request(self, messages: T.List[dict]) -> dict:
        request_dict = {
            'model': self._model,
            **({'temperature': self._model_temperature} if self._model_temperature is not None else {}),
            'messages': messages,
            **({'tools': [{'type': 'function', 'function': f['schema']} for f in self._functions.values()]} \
                    if self._functions else {})
        }
        
        # Special configurations for different models (only for litellm models)
        if "ollama" in self._model:
            request_dict['api_base'] = "http://localhost:11434"
        elif "deepseek" not in self._model.lower():
            # Only add API configurations for non-DeepSeek models that use litellm
            # DeepSeek models use direct OpenAI client with configs in client creation
            pass
        
        return request_dict


    async def _send_request(self, request: dict, ctx: object) -> litellm.ModelResponse|None:
        """Sends the LLM chat request, handling common failures and returning the response."""

        sleep = 1
        while True:
            try:
                # TODO also add request limit; could use 'await asyncio.gather(t.acquire(tokens), r.acquire())'
                # to acquire both
                if self.token_rate_limit:
                    try:
                        await self.token_rate_limit.acquire(count_tokens(self._model, request))
                    except ValueError as e:
                        self._log_msg(ctx, f"Error: too many tokens for rate limit ({e})")
                        return None # gives up this segment

                # Special handling for DeepSeek models - use direct OpenAI client approach
                if "deepseek" in self._model.lower():
                    import os
                    import openai
                    
                    # Use your exact pattern from test.py
                    client = openai.AsyncOpenAI(
                        api_key=os.getenv('coverup'), 
                        base_url=os.getenv("ANTHROPIC_BASE_URL")
                    )
                    
                    # Prepare messages exactly like your test.py
                    messages = request['messages']
                    
                    # Make the API call using your pattern
                    openai_params = {
                        'model': self._model,
                        'messages': messages,
                        'max_tokens': 1024
                    }
                    
                    # Add temperature if specified
                    if 'temperature' in request:
                        openai_params['temperature'] = request['temperature']
                    
                    # Add tools if specified  
                    if 'tools' in request:
                        openai_params['tools'] = request['tools']
                    
                    response = await client.chat.completions.create(**openai_params)
                    
                    return response
                else:
                    return await litellm.acreate(**request)

            except (litellm.exceptions.ServiceUnavailableError,
                    openai.RateLimitError,
                    openai.APITimeoutError) as e:

                # This message usually indicates out of money in account
                if 'You exceeded your current quota' in str(e):
                    self._log_msg(ctx, f"Failed: {type(e)} {e}")
                    raise

                self._log_msg(ctx, f"Error: {type(e)} {e}")

                import random
                sleep = min(sleep*2, self._max_backoff)
                sleep_time = random.uniform(sleep/2, sleep)
                self._signal_retry()
                await asyncio.sleep(sleep_time)

            except (openai.BadRequestError, litellm.exceptions.BadRequestError) as e:
                # usually "maximum context length" or model recognition issues
                self._log_msg(ctx, f"Error: {type(e)} {e}")
                return None # gives up this segment

            except (openai.AuthenticationError, litellm.exceptions.AuthenticationError) as e:
                self._log_msg(ctx, f"Failed: {type(e)} {e}")
                raise

            except (openai.APIConnectionError, litellm.exceptions.APIConnectionError) as e:
                self._log_msg(ctx, f"Error: {type(e)} {e}")
                # usually a server-side error... just retry right away
                self._signal_retry()

            except (openai.APIError, litellm.exceptions.APIError) as e:
                # APIError is the base class for all API errors;
                # we may be missing a more specific handler.
                print(f"Error: {type(e)} {e}; missing handler?")
                self._log_msg(ctx, f"Error: {type(e)} {e}")
                return None # gives up this segment


    def _call_function(self, ctx: object, tool_call) -> str:
        # Handle both litellm.ModelResponse and OpenAI response tool calls
        if hasattr(tool_call, 'function'):
            # OpenAI direct response format
            args = json.loads(tool_call.function.arguments)
            function_name = tool_call.function.name
        else:
            # litellm format - fallback
            args = json.loads(tool_call.function.arguments)
            function_name = tool_call.function.name
        print(f"tool_call: {tool_call}")
        
        function = self._functions[function_name]

        try:
            return str(function['function'](ctx=ctx, **args))
        except Exception as e:
            self._log_msg(ctx, f"""\
Error executing function "{function_name}": {e}
args:{args}

{traceback.format_exc()}
""")
            return f'Error executing function: {e}'


    async def chat(self, messages: list, *, ctx: T.Optional[object] = None) -> dict|None:
        """Chats with the LLM, sending the given messages, handling common failures and returning the response.
           Automatically calls any tool functions requested."""

        func_calls = 0
        while func_calls <= self._max_func_calls_per_chat:
            request = self._request(messages)
            self._log_json(ctx, request)

            if not (response := await self._send_request(request, ctx=ctx)):
                return None

            # Log response in proper format
            if "deepseek" in self._model.lower():
                message_data = {
                    "content": response.choices[0].message.content,
                    "role": response.choices[0].message.role
                }
                # Add tool_calls if present
                if response.choices[0].message.tool_calls:
                    message_data["tool_calls"] = []
                    for tool_call in response.choices[0].message.tool_calls:
                        message_data["tool_calls"].append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                
                log_response = {
                    "choices": [
                        {
                            "message": message_data,
                            "finish_reason": response.choices[0].finish_reason
                        }
                    ]
                }
                self._log_json(ctx, log_response)
            else:
                self._log_json(ctx, response.json())
            # Skip cost calculation for DeepSeek models
            if "deepseek" not in self._model.lower():
                try:
                    cost = litellm.completion_cost(response)
                    self._add_cost(cost)
                except Exception as e:
                    # Fallback cost calculation for other custom models
                    if hasattr(response, 'usage') and response.usage:
                        fallback_cost = compute_cost(response.usage.model_dump(), self._model)
                        if fallback_cost:
                            self._add_cost(fallback_cost)

            # Handle DeepSeek response format
            if "deepseek" in self._model.lower():
                # Convert response to dict format
                message_data = {
                    "content": response.choices[0].message.content,
                    "role": response.choices[0].message.role
                }
                # Add tool_calls if present
                if response.choices[0].message.tool_calls:
                    message_data["tool_calls"] = []
                    for tool_call in response.choices[0].message.tool_calls:
                        message_data["tool_calls"].append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                
                response_dict = {
                    "choices": [
                        {
                            "message": message_data,
                            "finish_reason": response.choices[0].finish_reason
                        }
                    ]
                }
                
                if response.choices[0].finish_reason != "tool_calls":
                    return response_dict
            else:
                if response.choices[0].finish_reason != "tool_calls":
                    return response.json()

            # Handle tool message format for DeepSeek
            if "deepseek" in self._model.lower():
                tool_message = {
                    "role": response.choices[0].message.role,
                    "content": "", # it's typically set to null, which upsets count_tokens
                }
                if response.choices[0].message.tool_calls:
                    tool_message["tool_calls"] = []
                    for tool_call in response.choices[0].message.tool_calls:
                        tool_message["tool_calls"].append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
            else:
                tool_message = response.choices[0].message.json()
            tool_message["content"] = "" # it's typically set to null, which upsets count_tokens
            messages.append(tool_message)

            for call in response.choices[0].message.tool_calls:
                func_calls += 1
                messages.append({
                    'tool_call_id': call.id,
                    'role': 'tool',
                    'name': call.function.name,
                    'content': self._call_function(ctx, call)
                })

        self._log_msg(ctx, f"Too many function call requests, giving up")
        return None
