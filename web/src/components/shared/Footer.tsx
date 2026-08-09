import Link from "next/link";

import { Logo } from "@/components/shared/Logo";

export function Footer() {
  return (
    <footer className="border-t border-line bg-card">
      <div className="page-container py-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <Logo />
            <p className="mt-1.5 max-w-sm text-sm text-slate">
              Trading signals ដែល AI បញ្ជាក់ ជាមួយចំណុចចូល បញ្ឈប់ខាត គោលដៅ
              និងការតាមដានលទ្ធផល។ ឥតគិតថ្លៃសម្រាប់បងប្អូនជួញដូរគ្រប់រូប — គ្មានគណនី គ្មាន
              ជញ្ជាំងបង់ប្រាក់។
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
            <Link href="/signals" className="font-medium text-slate hover:text-ink">
              Signals
            </Link>
            <Link href="/war-room" className="font-medium text-slate hover:text-ink">
              War Room
            </Link>
            <Link href="/track-record" className="font-medium text-slate hover:text-ink">
              កំណត់ត្រាលទ្ធផល
            </Link>
          </nav>
        </div>
        <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-slate">
          Signals គឺសម្រាប់គោលបំណងអប់រំ និងវិភាគតែប៉ុណ្ណោះ។ មិនមែនដំបូន្មានហិរញ្ញវត្ថុទេ។
          ការជួញដូរមានហានិភ័យ។ © {new Date().getFullYear()} Qauntify។
        </p>
      </div>
    </footer>
  );
}
