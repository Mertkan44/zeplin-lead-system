import type { AnchorHTMLAttributes } from 'react';

import { followLink } from '../lib/router';

export interface LinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  /** An app path such as /leads/57. */
  to: string;
}

/** An in-app link: a real <a href> (new tab, copy link work) that navigates without a reload. */
export function Link({ to, onClick, ...rest }: LinkProps) {
  return (
    <a
      href={to}
      onClick={event => {
        onClick?.(event);
        followLink(event, to);
      }}
      {...rest}
    />
  );
}
