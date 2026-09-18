import {routes} from './app.routes';

describe('application routes', () => {
    it('exposes privacy and terms pages without an authentication guard', () => {
        const privacy = routes.find(route => route.path === 'privacy');
        const terms = routes.find(route => route.path === 'terms');

        expect(privacy).toBeDefined();
        expect(privacy?.canActivate).toBeUndefined();
        expect(terms).toBeDefined();
        expect(terms?.canActivate).toBeUndefined();
    });
});