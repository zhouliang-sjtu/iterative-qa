"""命令行接口 - 提供交互式质量校验功能"""

import argparse
import sys
from typing import Optional

from iterative_qa import QAService


def main():
    parser = argparse.ArgumentParser(
        prog="iterative-qa",
        description="AI驱动的智能质量校验引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 执行第1轮全局质量校验
  iterative-qa --round 1
  
  # 指定项目路径
  iterative-qa --path /path/to/project --round 1
  
  # 生成详细报告
  iterative-qa --report --output report.md
  
  # 执行完整校验周期
  iterative-qa --full-cycle
  
  # 分析项目特征
  iterative-qa --analyze
        """
    )
    
    parser.add_argument(
        "--path", "-p",
        default=".",
        help="项目路径 (默认: 当前目录)"
    )
    
    parser.add_argument(
        "--round", "-r",
        type=int,
        default=1,
        help="校验轮次 (默认: 1)"
    )
    
    parser.add_argument(
        "--full-cycle", "-f",
        action="store_true",
        help="执行完整校验周期直到收敛"
    )
    
    parser.add_argument(
        "--analyze", "-a",
        action="store_true",
        help="仅分析项目特征"
    )
    
    parser.add_argument(
        "--report", "-o",
        action="store_true",
        help="生成质量报告"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="报告输出文件路径"
    )
    
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=10,
        help="最大校验轮次 (默认: 10)"
    )
    
    args = parser.parse_args()
    
    try:
        # 初始化服务
        qa_service = QAService(project_path=args.path)
        
        if args.analyze:
            # 仅分析项目特征
            profile = qa_service.analyze_project()
            print("=" * 60)
            print("项目特征分析结果")
            print("=" * 60)
            print(f"项目类型: {profile.project_type}")
            print(f"技术栈: {', '.join(profile.tech_stack)}")
            print(f"规模: {profile.scale}")
            print(f"复杂度: {profile.complexity}")
            print(f"领域: {profile.domain}")
            print(f"安全要求: {profile.security_requirements}/10")
            print(f"文件数量: {profile.file_count}")
            print(f"代码行数: {profile.lines_of_code}")
            print("=" * 60)
            
            # 显示推荐视角
            perspectives = qa_service.recommend_perspectives()
            print("\n推荐视角专家:")
            for i, perspective in enumerate(perspectives, 1):
                print(f"  {i}. {perspective}")
            
        elif args.full_cycle:
            # 执行完整校验周期
            print("=" * 60)
            print("开始完整校验周期")
            print("=" * 60)
            
            report = qa_service.run_full_cycle(max_rounds=args.max_rounds)
            print(report)
            
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(report)
                print(f"\n报告已保存到: {args.output}")
        
        else:
            # 执行指定轮次校验
            print(f"=" * 60)
            print(f"执行第 {args.round} 轮质量校验")
            print("=" * 60)
            
            result = qa_service.validate(round_number=args.round)
            
            print(f"\n校验状态: {result.status}")
            print(f"发现问题: {len(result.issues_found)}")
            
            if result.issues_found:
                print("\n问题详情:")
                for issue in result.issues_found:
                    print(f"\n  [{issue.severity.upper()}] {issue.check_name}")
                    print(f"    状态: {issue.status}")
                    print(f"    描述: {issue.message}")
                    if issue.remediation:
                        print(f"    修复建议: {issue.remediation}")
            
            # 生成报告
            if args.report:
                report = qa_service.generate_report()
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as f:
                        f.write(report)
                    print(f"\n报告已保存到: {args.output}")
                else:
                    print("\n" + "=" * 60)
                    print("质量报告")
                    print("=" * 60)
                    print(report)
        
        sys.exit(0)
        
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()