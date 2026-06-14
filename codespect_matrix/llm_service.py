"""大模型服务模块 - 支持多种大模型提供商的统一接口"""

import os
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 审查/分析专用温度 — 低温度确保输出一致性和精确性
DEFAULT_ANALYSIS_TEMPERATURE = 0.2


class LLMService:
    """大模型服务封装类"""
    
    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        """
        初始化大模型服务
        
        Args:
            provider: 模型提供商 (openai, anthropic, google, baidu, tongyi, zhipu, huggingface)
            api_key: API密钥
            model: 模型名称
        """
        self.provider = provider or os.getenv("LLM_PROVIDER", "openai")
        self.api_key = api_key or self._get_api_key()
        self.model = model or self._get_default_model()
        self.client = self._init_client()
        
    def _get_api_key(self) -> str:
        """根据提供商获取API密钥"""
        key_map = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "google": os.getenv("GOOGLE_API_KEY"),
            "baidu": os.getenv("BAIDU_API_KEY"),
            "tongyi": os.getenv("TONGYI_API_KEY"),
            "zhipu": os.getenv("ZHIPU_API_KEY"),
            "huggingface": os.getenv("HUGGINGFACE_API_KEY"),
        }
        return key_map.get(self.provider)
    
    def _get_default_model(self) -> str:
        """获取默认模型名称"""
        model_map = {
            "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
            "google": os.getenv("GOOGLE_MODEL", "gemini-pro"),
            "baidu": os.getenv("BAIDU_MODEL", "ERNIE-Bot-4.0"),
            "tongyi": os.getenv("TONGYI_MODEL", "qwen-plus"),
            "zhipu": os.getenv("ZHIPU_MODEL", "glm-4"),
            "huggingface": os.getenv("HUGGINGFACE_MODEL", "mistralai/Mistral-7B-v0.3"),
        }
        return model_map.get(self.provider, "gpt-4o-mini")
    
    def _init_client(self):
        """初始化客户端"""
        if not self.api_key:
            raise ValueError(f"未配置 {self.provider} 的 API 密钥")
        
        try:
            if self.provider == "openai":
                from openai import OpenAI
                base_url = os.getenv("OPENAI_API_BASE")
                return OpenAI(api_key=self.api_key, base_url=base_url)
            
            elif self.provider == "anthropic":
                from anthropic import Anthropic
                return Anthropic(api_key=self.api_key)
            
            elif self.provider == "google":
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                return genai.GenerativeModel(self.model)
            
            elif self.provider == "baidu":
                from qianfan import ChatCompletion
                return ChatCompletion
            
            elif self.provider == "tongyi":
                from dashscope import Generation
                return Generation
            
            elif self.provider == "zhipu":
                from zhipuai import ZhipuAI
                return ZhipuAI(api_key=self.api_key)
            
            elif self.provider == "huggingface":
                from transformers import pipeline
                return pipeline("text-generation", model=self.model)
            
            else:
                raise ValueError(f"不支持的模型提供商: {self.provider}")
                
        except ImportError as e:
            raise ImportError(f"缺少 {self.provider} 的依赖库: {e}")
    
    def generate(self, prompt: str, **kwargs) -> str:
        """
        生成文本响应
        
        Args:
            prompt: 提示词
            **kwargs: 额外参数（temperature, max_tokens等）
        
        Returns:
            生成的文本
        """
        temperature = kwargs.get("temperature", float(os.getenv("OPENAI_TEMPERATURE", "0.7")))
        max_tokens = kwargs.get("max_tokens", int(os.getenv("OPENAI_MAX_TOKENS", "4096")))
        
        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
            
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.content[0].text
            
            elif self.provider == "google":
                response = self.client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
                )
                return response.text
            
            elif self.provider == "baidu":
                response = self.client.do(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.get("result", {}).get("content", "")
            
            elif self.provider == "tongyi":
                response = self.model.call(
                    model=self.model,
                    input=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.output.text
            
            elif self.provider == "zhipu":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
            
            elif self.provider == "huggingface":
                response = self.client(
                    prompt,
                    max_length=max_tokens,
                    temperature=temperature,
                    do_sample=True,
                )
                return response[0]["generated_text"]
            
            else:
                raise ValueError(f"不支持的模型提供商: {self.provider}")
                
        except Exception as e:
            raise RuntimeError(f"大模型调用失败: {e}")
    
    def analyze_project(self, project_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用大模型分析项目特征
        
        Args:
            project_features: 项目特征字典
        
        Returns:
            分析结果
        """
        prompt = f"""
        作为一位资深的软件架构师和质量保证专家，请分析以下项目特征：
        
        项目信息：
        - 项目类型: {project_features.get('project_type', '')}
        - 技术栈: {', '.join(project_features.get('tech_stack', []))}
        - 规模: {project_features.get('scale', '')}
        - 复杂度: {project_features.get('complexity', '')}
        - 业务领域: {project_features.get('domain', '')}
        - 安全要求等级: {project_features.get('security_requirements', 5)}/10
        - 文件数量: {project_features.get('file_count', 0)}
        - 代码行数: {project_features.get('lines_of_code', 0)}
        
        请提供以下分析：
        1. 项目质量风险评估（高/中/低风险领域）
        2. 推荐的质量检查重点
        3. 潜在的技术债务
        4. 优化建议
        
        请用JSON格式输出，包含risk_assessment, focus_areas, technical_debt, recommendations字段。
        """
        
        result = self.generate(prompt, temperature=0.3, max_tokens=2048)
        return self._parse_json(result)
    
    def generate_report(self, validation_results: List[Dict[str, Any]], project_profile: Dict[str, Any]) -> str:
        """
        使用大模型生成质量报告
        
        Args:
            validation_results: 验证结果列表
            project_profile: 项目特征
        
        Returns:
            格式化的报告文本
        """
        results_str = "\n".join([
            f"- [{r.get('severity', '')}] {r.get('check_name', '')}: {r.get('message', '')}"
            for r in validation_results
        ])
        
        prompt = f"""
        作为一位专业的质量保证工程师，请基于以下验证结果生成一份详细的质量报告：
        
        项目信息：
        - 项目类型: {project_profile.get('project_type', '')}
        - 技术栈: {', '.join(project_profile.get('tech_stack', []))}
        - 规模: {project_profile.get('scale', '')}
        - 领域: {project_profile.get('domain', '')}
        
        验证问题列表：
        {results_str}
        
        请生成一份专业的质量报告，包含：
        1. 执行摘要
        2. 问题分类统计
        3. 风险评估
        4. 修复建议优先级
        5. 改进路线图
        
        报告格式：markdown
        """
        
        return self.generate(prompt, temperature=0.5, max_tokens=4096)
    
    def generate_fix_plan(self, issues: List[Dict[str, Any]], project_path: str) -> List[Dict[str, Any]]:
        """
        使用大模型生成具体的修复方案
        
        Args:
            issues: 问题列表，每个问题包含 check_name, message, severity, remediation
            project_path: 项目根目录
        
        Returns:
            修复动作列表 [{file_path, line_start, line_end, old_code, new_code, description, auto_safe, ...}]
        """
        import glob as glob_mod
        
        # 收集项目中所有 .py 文件的前 30 行作为上下文
        file_map = {}
        for filepath in glob_mod.glob(os.path.join(project_path, "**", "*.py"), recursive=True):
            relpath = os.path.relpath(filepath, project_path)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if len(content) < 8000:
                        file_map[relpath] = content
                    else:
                        # 只取首尾，中间给摘要
                        file_map[relpath] = (
                            content[:3000] + "\n# ... (中间省略) ...\n" + content[-2000:]
                        )
            except Exception:
                continue
        
        # 仅保留内容最相关的 20 个文件（优先小文件）
        relevant_files = sorted(file_map.items(), key=lambda x: len(x[1]))[:20]
        files_context = ""
        for fname, fcontent in relevant_files:
            files_context += f"\n\n=== FILE: {fname} ===\n{fcontent}"
        if len(files_context) > 24000:
            files_context = files_context[:24000] + "\n# ... 更多文件已省略 ..."
        
        issues_text = "\n".join([
            f"- [{i.get('severity','info')}] {i.get('check_name','')}: {i.get('message','')}\n  修复建议: {i.get('remediation','无')}"
            for i in issues
        ])
        
        prompt = f"""你是一位高级软件工程师和代码审查专家。以下是代码扫描发现的问题和项目源码，请为每个问题生成精确的修复方案。

## 项目文件:
{files_context}

## 扫描发现的问题:
{issues_text}

## 要求:
请分析每个问题，找到源码中的具体位置，生成修复代码。输出一个 JSON 数组，每个元素格式如下：

{{
  "file_path": "相对于项目的文件路径",
  "line_start": 起始行号(1-based),
  "line_end": 结束行号,
  "old_code": "要被替换的原始代码（必须与源文件完全一致）",
  "new_code": "替换后的新代码",
  "description": "中文修复说明",
  "auto_safe": true/false  # 简单替换(如加注释/改变量名/加try-except)为true; 涉及逻辑更改/架构调整为false
}}

注意:
1. old_code 必须与源文件中的代码一字不差
2. 保持原有缩进风格
3. 只修复具体问题，不要额外重构
4. 如果某个问题无法确定具体代码位置，跳过它
5. 只返回 JSON 数组，不要其他文字

JSON:"""
        
        result = self.generate(prompt, temperature=DEFAULT_ANALYSIS_TEMPERATURE, max_tokens=8192)
        return self._parse_json_array(result)
    
    def _parse_json_array(self, text: str) -> List[Dict[str, Any]]:
        """解析JSON数组响应"""
        import json
        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end != 0:
                return json.loads(text[start:end])
            return []
        except json.JSONDecodeError:
            return []
    
    def _parse_json(self, text: str) -> Dict[str, Any]:
        """解析JSON响应"""
        import json
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end != 0:
                return json.loads(text[start:end])
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "JSON解析失败", "raw_response": text}


# 工厂函数
def create_llm_service(provider: str = None) -> LLMService:
    """
    创建大模型服务实例
    
    Args:
        provider: 模型提供商
    
    Returns:
        LLMService实例
    """
    return LLMService(provider)


# 全局单例
_llm_service = None

def get_llm_service() -> LLMService:
    """获取全局大模型服务实例"""
    global _llm_service
    if _llm_service is None:
        try:
            _llm_service = LLMService()
        except Exception as e:
            # 如果环境变量未配置，返回None（兼容Trae CN环境）
            return None
    return _llm_service


__all__ = ["LLMService", "create_llm_service", "get_llm_service"]